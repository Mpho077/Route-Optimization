import logging
import math
from datetime import date, timedelta

from odoo import api, models

from ..providers.provider_factory import get_routing_provider
from ..providers.base_provider import RoutingProviderError

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurable weight constants — can be overridden via system parameters
# ---------------------------------------------------------------------------
DEFAULT_WEIGHTS = {
    'distance_penalty_per_km': 2.0,       # points deducted per km of driving
    'overdue_base': 1.5,                  # exponential base for overdue scoring
    'overdue_multiplier': 10.0,           # multiplied with the exponential term
    'critical_overdue_days': 14,          # days overdue to trigger "magnet" effect
    'cluster_bonus': 5.0,                 # bonus for jobs in same zip code
    'job_type_weights': {                 # base priority per job category
        'installation': 10,
        'cleaning': 10,
        'routine': 15,
        'service': 15,
        'renewal': 8,
        'winback': 8,
    },
}


class RouteOptimizer(models.AbstractModel):
    """Transient service model that orchestrates daily route optimization.

    Not stored in DB — used purely for computation via ``self.env['route.optimizer']``.
    """

    _name = 'route.optimizer'
    _description = 'Route Optimization Engine'

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def optimize_daily_routes(self, target_date=None):
        """Main entry point called by the cron job.

        For every technician with tasks on ``target_date``, compute the
        optimal driving sequence and write ``route_order`` on each task.

        Args:
            target_date (date, optional): Defaults to today.

        Returns:
            list[dict]: Summary per technician.
        """
        target_date = target_date or date.today()
        _logger.info("Starting route optimization for %s", target_date)

        try:
            provider = get_routing_provider(self.env)
        except RoutingProviderError as exc:
            _logger.error("Cannot start optimization — provider error: %s", exc)
            return []

        results = []
        technicians = self._get_technicians_with_tasks(target_date)

        for tech in technicians:
            tasks = self._get_tasks_for_technician(tech, target_date)
            if len(tasks) < 2:
                # Single task — no optimisation needed
                if tasks:
                    tasks[0].route_order = 1
                continue

            try:
                result = self._optimize_for_technician(provider, tech, tasks, target_date)
                results.append(result)
            except RoutingProviderError as exc:
                _logger.error(
                    "Route optimization failed for %s: %s", tech.name, exc
                )

        # Create / update route plan records
        self._save_route_plans(results, target_date)
        _logger.info("Route optimization complete for %s — %d technicians processed", target_date, len(results))
        return results

    # ------------------------------------------------------------------
    # Internal: per-technician optimization
    # ------------------------------------------------------------------
    def _optimize_for_technician(self, provider, technician, tasks, target_date):
        """Compute optimal route for one technician on a given day."""

        depot = self._get_depot_coords(technician)
        task_coords = []
        valid_tasks = []

        for task in tasks:
            coords = self._get_task_coords(task)
            if coords:
                task_coords.append(coords)
                valid_tasks.append(task)
            else:
                _logger.warning("Task %s has no coordinates — skipped.", task.id)

        if not valid_tasks:
            return {'technician': technician, 'tasks': [], 'total_duration': 0}

        # Build coordinate list: depot + all tasks
        all_coords = [depot] + task_coords

        # Get NxN time matrix from provider
        matrix_result = provider.get_distance_matrix(all_coords)
        durations = matrix_result['durations']

        # Score each task (SLA urgency + type priority)
        scores = self._score_tasks(valid_tasks, target_date)

        # Check for "magnet" tasks (critically overdue)
        magnets = self._identify_magnets(valid_tasks, scores, target_date)

        # Solve: nearest-neighbour heuristic with SLA-weighted bias
        ordered_indices = self._solve_weighted_tsp(
            durations, scores, magnets, valid_tasks
        )

        # Write route_order on tasks
        for order_pos, task_idx in enumerate(ordered_indices, start=1):
            valid_tasks[task_idx].route_order = order_pos

        # Get full route geometry for map display
        ordered_coords = [depot] + [task_coords[i] for i in ordered_indices]
        try:
            route_info = provider.get_route(ordered_coords)
        except RoutingProviderError:
            route_info = {'total_duration': 0, 'total_distance': 0, 'geometry': None, 'legs': []}

        return {
            'technician': technician,
            'tasks': [valid_tasks[i] for i in ordered_indices],
            'total_duration': route_info.get('total_duration', 0),
            'total_distance': route_info.get('total_distance', 0),
            'geometry': route_info.get('geometry'),
            'legs': route_info.get('legs', []),
        }

    # ------------------------------------------------------------------
    # Scoring engine
    # ------------------------------------------------------------------
    def _score_tasks(self, tasks, target_date):
        """Compute a priority score for each task.

        Returns:
            list[float]: Score per task (higher = more urgent).
        """
        w = self._get_weights()
        scores = []

        for task in tasks:
            base = w['job_type_weights'].get(task.job_category, 10)

            # Overdue calculation
            overdue_days = 0
            if task.planned_date_begin:
                ideal = task.planned_date_begin.date() if hasattr(task.planned_date_begin, 'date') else task.planned_date_begin
                overdue_days = max(0, (target_date - ideal).days)

            if overdue_days > 0:
                urgency = w['overdue_multiplier'] * (w['overdue_base'] ** overdue_days)
            else:
                urgency = 0

            score = base + urgency
            scores.append(score)

        return scores

    def _identify_magnets(self, tasks, scores, target_date):
        """Find tasks that are critically overdue and must be anchored.

        Returns:
            set[int]: Indices of magnet tasks.
        """
        w = self._get_weights()
        threshold = w['critical_overdue_days']
        magnets = set()

        for idx, task in enumerate(tasks):
            if task.planned_date_begin:
                ideal = task.planned_date_begin.date() if hasattr(task.planned_date_begin, 'date') else task.planned_date_begin
                overdue_days = (target_date - ideal).days
                if overdue_days >= threshold:
                    magnets.add(idx)

        return magnets

    # ------------------------------------------------------------------
    # TSP solver — SLA-weighted nearest neighbour
    # ------------------------------------------------------------------
    def _solve_weighted_tsp(self, durations, scores, magnets, tasks):
        """Greedy nearest-neighbour with urgency bias.

        1. Magnet tasks are placed first (sorted by score descending).
        2. Remaining tasks are visited in nearest-neighbour order,
           but distance is penalised/rewarded by the SLA score.

        Args:
            durations: NxN matrix (index 0 = depot).
            scores: Per-task urgency scores.
            magnets: Set of task indices that must be visited.
            tasks: Task recordset (for zip-code clustering).

        Returns:
            list[int]: Task indices in optimal visit order.
        """
        w = self._get_weights()
        n_tasks = len(scores)
        visited = [False] * n_tasks
        route = []

        # --- Phase 1: Force magnets ---
        magnet_list = sorted(magnets, key=lambda i: scores[i], reverse=True)
        current_matrix_idx = 0  # start at depot

        for m_idx in magnet_list:
            route.append(m_idx)
            visited[m_idx] = True
            current_matrix_idx = m_idx + 1  # +1 because depot is index 0

        # --- Phase 2: Fill remaining with weighted nearest-neighbour ---
        if not route:
            current_matrix_idx = 0  # depot

        for _ in range(n_tasks - len(route)):
            best_idx = None
            best_cost = float('inf')

            for j in range(n_tasks):
                if visited[j]:
                    continue

                travel_time = durations[current_matrix_idx][j + 1]  # +1 for depot offset
                if travel_time is None:
                    continue

                # Cluster bonus: same zip code as last visited
                cluster_bonus = 0
                if route:
                    last_task = tasks[route[-1]]
                    candidate = tasks[j]
                    if (last_task.partner_id.zip and candidate.partner_id.zip
                            and last_task.partner_id.zip == candidate.partner_id.zip):
                        cluster_bonus = w['cluster_bonus']

                # Effective cost = travel penalty − urgency score − cluster bonus
                distance_km = travel_time / 60.0  # rough approximation
                cost = (distance_km * w['distance_penalty_per_km']) - scores[j] - cluster_bonus
                if cost < best_cost:
                    best_cost = cost
                    best_idx = j

            if best_idx is not None:
                route.append(best_idx)
                visited[best_idx] = True
                current_matrix_idx = best_idx + 1

        return route

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_technicians_with_tasks(self, target_date):
        """Find all technicians that have field service tasks for the date."""
        tasks = self.env['project.task'].search([
            ('is_fsm', '=', True),
            ('planned_date_begin', '>=', str(target_date)),
            ('planned_date_begin', '<', str(target_date + timedelta(days=1))),
            ('stage_id.is_close', '=', False),
        ])
        return tasks.mapped('user_ids')

    def _get_tasks_for_technician(self, technician, target_date):
        """Fetch all open tasks assigned to a technician for the target date."""
        return self.env['project.task'].search([
            ('is_fsm', '=', True),
            ('user_ids', 'in', [technician.id]),
            ('planned_date_begin', '>=', str(target_date)),
            ('planned_date_begin', '<', str(target_date + timedelta(days=1))),
            ('stage_id.is_close', '=', False),
        ], order='planned_date_begin asc')

    def _get_depot_coords(self, technician):
        """Return the start location (lng, lat) for a technician.

        Falls back to company address if no home address is set.
        """
        partner = technician.partner_id
        if partner and partner.partner_latitude and partner.partner_longitude:
            return (partner.partner_longitude, partner.partner_latitude)

        company = technician.company_id or self.env.company
        if company.partner_id.partner_latitude and company.partner_id.partner_longitude:
            return (company.partner_id.partner_longitude, company.partner_id.partner_latitude)

        _logger.warning("No coordinates for technician %s — using default.", technician.name)
        return (10.7522, 59.9139)  # Oslo fallback

    def _get_task_coords(self, task):
        """Return (lng, lat) for a task's customer address."""
        partner = task.partner_id
        if partner and partner.partner_latitude and partner.partner_longitude:
            return (partner.partner_longitude, partner.partner_latitude)
        return None

    def _get_weights(self):
        """Load weight configuration from system parameters, with defaults."""
        ICP = self.env['ir.config_parameter'].sudo()
        w = dict(DEFAULT_WEIGHTS)
        w['distance_penalty_per_km'] = float(
            ICP.get_param('route_optimization.distance_penalty_per_km', w['distance_penalty_per_km']))
        w['overdue_base'] = float(
            ICP.get_param('route_optimization.overdue_base', w['overdue_base']))
        w['overdue_multiplier'] = float(
            ICP.get_param('route_optimization.overdue_multiplier', w['overdue_multiplier']))
        w['critical_overdue_days'] = int(
            ICP.get_param('route_optimization.critical_overdue_days', w['critical_overdue_days']))
        w['cluster_bonus'] = float(
            ICP.get_param('route_optimization.cluster_bonus', w['cluster_bonus']))
        return w

    def _save_route_plans(self, results, target_date):
        """Create or update route.plan records for the day."""
        RoutePlan = self.env['route.plan']
        for res in results:
            tech = res['technician']
            existing = RoutePlan.search([
                ('technician_id', '=', tech.id),
                ('date', '=', str(target_date)),
            ], limit=1)

            vals = {
                'technician_id': tech.id,
                'date': target_date,
                'total_duration': res.get('total_duration', 0),
                'total_distance': res.get('total_distance', 0),
                'route_geometry': str(res.get('geometry', '')),
                'task_ids': [(6, 0, [t.id for t in res.get('tasks', [])])],
                'state': 'optimized',
            }

            if existing:
                existing.write(vals)
            else:
                RoutePlan.create(vals)
