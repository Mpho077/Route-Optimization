"""Tests for the route optimization engine (scoring, magnets, TSP solver).

Mocks the routing provider so tests run without OSRM/Google.
Run with:  odoo-bin -d testdb --test-tags route_optimization -i route_optimization
"""
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock

from odoo.tests.common import TransactionCase, tagged


def _make_mock_provider(durations_matrix):
    """Create a mock provider that returns a fixed distance matrix."""
    provider = MagicMock()
    provider.get_distance_matrix.return_value = {
        'durations': durations_matrix,
        'distances': durations_matrix,  # simplified: durations == distances for tests
    }
    provider.get_route.return_value = {
        'total_duration': 1200,
        'total_distance': 15000,
        'geometry': {'type': 'LineString', 'coordinates': []},
        'legs': [],
    }
    return provider


@tagged('post_install', '-at_install', 'route_optimization')
class TestRouteOptimizer(TransactionCase):
    """Test the optimization engine logic."""

    def setUp(self):
        super().setUp()
        self.optimizer = self.env['route.optimizer']

        # Create a test FSM project
        self.project = self.env['project.project'].create({
            'name': 'Test FSM Project',
            'is_fsm': True,
        })

        # Create test technician
        self.tech_user = self.env['res.users'].create({
            'name': 'Test Technician',
            'login': 'test_tech_route_opt',
            'email': 'tech@test.com',
        })
        # Set coordinates on technician's partner (depot)
        self.tech_user.partner_id.write({
            'partner_latitude': 59.9139,
            'partner_longitude': 10.7522,
        })

        # Create test customers with coordinates
        self.customers = []
        coords = [
            (59.92, 10.76, '0150'),  # close
            (59.93, 10.78, '0150'),  # same zip as above
            (59.95, 10.85, '0250'),  # farther
            (59.90, 10.70, '0350'),  # different area
        ]
        for i, (lat, lng, zipcode) in enumerate(coords):
            partner = self.env['res.partner'].create({
                'name': f'Customer {i+1}',
                'partner_latitude': lat,
                'partner_longitude': lng,
                'zip': zipcode,
                'street': f'Test Street {i+1}',
            })
            self.customers.append(partner)

    def _create_task(self, partner, category='routine', days_overdue=0, hours=1.0):
        """Helper to create a field service task."""
        planned = datetime.combine(
            date.today() - timedelta(days=days_overdue),
            datetime.min.time().replace(hour=8),
        )
        return self.env['project.task'].create({
            'name': f'Task for {partner.name}',
            'project_id': self.project.id,
            'partner_id': partner.id,
            'user_ids': [(4, self.tech_user.id)],
            'is_fsm': True,
            'job_category': category,
            'planned_date_begin': planned,
            'estimated_duration_hours': hours,
        })

    # -----------------------------------------------------------------
    # Scoring Tests
    # -----------------------------------------------------------------
    def test_score_no_overdue(self):
        """Task not overdue should get only base priority score."""
        task = self._create_task(self.customers[0], 'routine', days_overdue=0)
        scores = self.optimizer._score_tasks(task, date.today())
        self.assertEqual(len(scores), 1)
        # routine base = 15, no overdue bonus
        self.assertEqual(scores[0], 15)

    def test_score_overdue_increases(self):
        """Overdue tasks should score higher than on-time tasks."""
        task_ok = self._create_task(self.customers[0], 'routine', days_overdue=0)
        task_late = self._create_task(self.customers[1], 'routine', days_overdue=5)

        scores = self.optimizer._score_tasks(task_ok | task_late, date.today())
        self.assertGreater(scores[1], scores[0])

    def test_score_exponential_overdue(self):
        """10 days overdue should score much higher than 3 days overdue."""
        task_3d = self._create_task(self.customers[0], 'routine', days_overdue=3)
        task_10d = self._create_task(self.customers[1], 'routine', days_overdue=10)

        scores = self.optimizer._score_tasks(task_3d | task_10d, date.today())
        # With base=1.5, multiplier=10: 10*(1.5^10) >> 10*(1.5^3)
        self.assertGreater(scores[1], scores[0] * 3)

    def test_job_type_weights(self):
        """Routine tasks should score higher than renewal tasks (base weight)."""
        task_routine = self._create_task(self.customers[0], 'routine', days_overdue=0)
        task_renewal = self._create_task(self.customers[1], 'renewal', days_overdue=0)

        scores = self.optimizer._score_tasks(task_routine | task_renewal, date.today())
        self.assertGreater(scores[0], scores[1])  # routine=15, renewal=8

    # -----------------------------------------------------------------
    # Magnet Detection Tests
    # -----------------------------------------------------------------
    def test_magnet_detection(self):
        """Tasks overdue by 14+ days should be flagged as magnets."""
        task_ok = self._create_task(self.customers[0], 'routine', days_overdue=5)
        task_critical = self._create_task(self.customers[1], 'routine', days_overdue=16)

        all_tasks = task_ok | task_critical
        scores = self.optimizer._score_tasks(all_tasks, date.today())
        magnets = self.optimizer._identify_magnets(all_tasks, scores, date.today())

        self.assertNotIn(0, magnets)  # 5 days — not a magnet
        self.assertIn(1, magnets)  # 16 days — IS a magnet

    def test_is_route_magnet_computed_field(self):
        """The computed is_route_magnet field on the task model should work."""
        task = self._create_task(self.customers[0], 'routine', days_overdue=20)
        task.invalidate_recordset()
        self.assertTrue(task.is_route_magnet)

    # -----------------------------------------------------------------
    # TSP Solver Tests
    # -----------------------------------------------------------------
    def test_tsp_solver_basic_ordering(self):
        """Solver should produce a valid permutation of all task indices."""
        # 4x4 matrix (depot + 3 tasks), times in seconds
        durations = [
            [0, 100, 500, 300],
            [100, 0, 400, 200],
            [500, 400, 0, 350],
            [300, 200, 350, 0],
        ]
        scores = [10, 10, 10]  # equal priority
        magnets = set()

        tasks = []
        for i in range(3):
            tasks.append(self._create_task(self.customers[i], 'routine', days_overdue=0))
        task_records = tasks[0] | tasks[1] | tasks[2]

        result = self.optimizer._solve_weighted_tsp(durations, scores, magnets, task_records)
        self.assertEqual(len(result), 3)
        self.assertEqual(sorted(result), [0, 1, 2])  # all tasks visited

    def test_tsp_magnet_prioritized(self):
        """Magnet tasks should appear first in the route."""
        durations = [
            [0, 100, 500, 300],
            [100, 0, 400, 200],
            [500, 400, 0, 350],
            [300, 200, 350, 0],
        ]
        scores = [10, 10, 50]  # task 2 has high urgency
        magnets = {2}  # task 2 is a magnet

        tasks = []
        for i in range(3):
            tasks.append(self._create_task(self.customers[i], 'routine', days_overdue=0))
        task_records = tasks[0] | tasks[1] | tasks[2]

        result = self.optimizer._solve_weighted_tsp(durations, scores, magnets, task_records)
        self.assertEqual(result[0], 2)  # magnet must be first

    # -----------------------------------------------------------------
    # Full Integration (mocked provider)
    # -----------------------------------------------------------------
    @patch('odoo.addons.route_optimization.models.route_optimizer.get_routing_provider')
    def test_full_optimization_creates_route_plan(self, mock_get_provider):
        """Full optimize_daily_routes should create a route.plan record."""
        # 5x5 matrix: depot + 4 tasks
        matrix = [
            [0, 100, 200, 300, 400],
            [100, 0, 150, 250, 350],
            [200, 150, 0, 100, 200],
            [300, 250, 100, 0, 150],
            [400, 350, 200, 150, 0],
        ]
        mock_get_provider.return_value = _make_mock_provider(matrix)

        # Create 4 tasks for today
        for i, cust in enumerate(self.customers):
            self._create_task(cust, 'routine', days_overdue=i * 3)

        self.optimizer.optimize_daily_routes(target_date=date.today())

        # A route plan should now exist
        plan = self.env['route.plan'].search([
            ('technician_id', '=', self.tech_user.id),
            ('date', '=', date.today()),
        ])
        self.assertTrue(plan.exists())
        self.assertEqual(plan.state, 'optimized')
        # All 4 tasks should be linked
        self.assertEqual(len(plan.task_ids), 4)
        # All tasks should have route_order set
        for task in plan.task_ids:
            self.assertGreater(task.route_order, 0)

    @patch('odoo.addons.route_optimization.models.route_optimizer.get_routing_provider')
    def test_reoptimize_updates_existing_plan(self, mock_get_provider):
        """Running optimization twice should update, not duplicate, the plan."""
        matrix = [
            [0, 100, 200],
            [100, 0, 150],
            [200, 150, 0],
        ]
        mock_get_provider.return_value = _make_mock_provider(matrix)

        self._create_task(self.customers[0], 'routine', days_overdue=0)
        self._create_task(self.customers[1], 'routine', days_overdue=0)

        self.optimizer.optimize_daily_routes(target_date=date.today())
        self.optimizer.optimize_daily_routes(target_date=date.today())

        plans = self.env['route.plan'].search([
            ('technician_id', '=', self.tech_user.id),
            ('date', '=', date.today()),
        ])
        self.assertEqual(len(plans), 1, "Should not create duplicate plans")

    @patch('odoo.addons.route_optimization.models.route_optimizer.get_routing_provider')
    def test_single_task_no_crash(self, mock_get_provider):
        """Single task should get route_order=1 without calling the provider."""
        mock_get_provider.return_value = _make_mock_provider([])

        task = self._create_task(self.customers[0], 'routine', days_overdue=0)
        self.optimizer.optimize_daily_routes(target_date=date.today())

        task.invalidate_recordset()
        self.assertEqual(task.route_order, 1)
        # Provider should NOT have been called for a single task
        mock_get_provider.return_value.get_distance_matrix.assert_not_called()


@tagged('post_install', '-at_install', 'route_optimization')
class TestRoutePlan(TransactionCase):
    """Test route.plan model methods."""

    def test_duration_display(self):
        """Duration display should format seconds as Xh Ym."""
        plan = self.env['route.plan'].create({
            'date': date.today(),
            'technician_id': self.env.user.id,
            'total_duration': 5430,  # 1h 30m 30s
            'total_distance': 25000,
        })
        self.assertEqual(plan.total_duration_display, '1h 30m')
        self.assertEqual(plan.total_distance_display, '25.0 km')

    def test_unique_constraint(self):
        """Cannot create two plans for the same technician on the same day."""
        from odoo.exceptions import ValidationError
        from psycopg2 import IntegrityError

        self.env['route.plan'].create({
            'date': date.today(),
            'technician_id': self.env.user.id,
        })
        with self.assertRaises(Exception):  # IntegrityError wrapped by Odoo
            self.env['route.plan'].create({
                'date': date.today(),
                'technician_id': self.env.user.id,
            })
