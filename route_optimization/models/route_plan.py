from odoo import api, fields, models


class RoutePlan(models.Model):
    _name = 'route.plan'
    _description = 'Daily Route Plan'
    _order = 'date desc, technician_id'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        index=True,
    )
    technician_id = fields.Many2one(
        'res.users',
        string='Technician',
        required=True,
        index=True,
    )
    task_ids = fields.One2many(
        'project.task',
        'route_plan_id',
        string='Tasks',
    )
    task_count = fields.Integer(
        compute='_compute_task_count',
        string='# Tasks',
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('optimized', 'Optimized'),
            ('in_progress', 'In Progress'),
            ('done', 'Completed'),
        ],
        string='Status',
        default='draft',
    )
    total_duration = fields.Float(
        string='Total Drive Time (s)',
        help='Total estimated driving time in seconds.',
    )
    total_distance = fields.Float(
        string='Total Distance (m)',
        help='Total estimated driving distance in meters.',
    )
    total_duration_display = fields.Char(
        string='Drive Time',
        compute='_compute_duration_display',
    )
    total_distance_display = fields.Char(
        string='Distance',
        compute='_compute_distance_display',
    )
    route_geometry = fields.Text(
        string='Route Geometry',
        help='GeoJSON or encoded polyline of the optimized route.',
    )

    @api.depends('date', 'technician_id')
    def _compute_name(self):
        for plan in self:
            tech_name = plan.technician_id.name or 'Unassigned'
            plan.name = f"{plan.date} — {tech_name}"

    def _compute_task_count(self):
        for plan in self:
            plan.task_count = len(plan.task_ids)

    def _compute_duration_display(self):
        for plan in self:
            mins = int(plan.total_duration / 60)
            plan.total_duration_display = f"{mins // 60}h {mins % 60}m"

    def _compute_distance_display(self):
        for plan in self:
            km = plan.total_distance / 1000.0
            plan.total_distance_display = f"{km:.1f} km"

    _sql_constraints = [
        ('unique_tech_date', 'UNIQUE(technician_id, date)',
         'Only one route plan per technician per day is allowed.'),
    ]

    def action_reoptimize(self):
        """Re-run optimization for this plan's technician and date."""
        self.ensure_one()
        optimizer = self.env['route.optimizer']
        optimizer.optimize_daily_routes(target_date=self.date)

    def action_view_map(self):
        """Open the map view for this route plan."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/route/map/{self.id}',
            'target': 'new',
        }

    def get_map_data(self):
        """Return data for the Leaflet map widget.

        Called from both the OWL JS widget and the HTTP controller.
        """
        self.ensure_one()
        import json

        tasks_data = []
        for task in self.task_ids.sorted('route_order'):
            partner = task.partner_id
            tasks_data.append({
                'id': task.id,
                'name': task.name or '',
                'order': task.route_order,
                'partner': partner.name if partner else '',
                'category': task.job_category or '',
                'lat': partner.partner_latitude if partner else 0,
                'lng': partner.partner_longitude if partner else 0,
                'is_magnet': task.is_route_magnet,
            })

        geometry = None
        if self.route_geometry:
            try:
                geometry = json.loads(self.route_geometry)
            except (json.JSONDecodeError, TypeError):
                geometry = None

        return {
            'plan_id': self.id,
            'technician': self.technician_id.name or '',
            'date': str(self.date),
            'tasks': tasks_data,
            'geometry': geometry,
            'total_duration': self.total_duration,
            'total_distance': self.total_distance,
        }
