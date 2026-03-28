from odoo import api, fields, models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    # --- Route Optimization Fields ---
    route_order = fields.Integer(
        string='Route Order',
        default=0,
        help='Optimized driving sequence position for this task. '
             'Lower = visit earlier. Set automatically by the route optimizer.',
    )
    job_category = fields.Selection(
        [
            ('installation', 'Installation'),
            ('cleaning', 'Cleaning'),
            ('routine', 'Routine Visit'),
            ('service', 'Service Visit'),
            ('renewal', 'Renewal'),
            ('winback', 'Win-back'),
        ],
        string='Job Category',
        default='routine',
        help='Used by the route optimizer to assign priority weights.',
    )
    estimated_duration_hours = fields.Float(
        string='Est. Duration (hrs)',
        default=1.0,
        help='Expected time to complete this job on-site.',
    )
    route_plan_id = fields.Many2one(
        'route.plan',
        string='Route Plan',
        ondelete='set null',
    )
    is_route_magnet = fields.Boolean(
        string='Route Magnet',
        compute='_compute_is_route_magnet',
        store=True,
        help='True if this task is critically overdue and must be anchored in the schedule.',
    )
    overdue_days = fields.Integer(
        string='Days Overdue',
        compute='_compute_overdue_days',
        store=True,
    )

    @api.depends('planned_date_begin')
    def _compute_overdue_days(self):
        today = fields.Date.context_today(self)
        for task in self:
            if task.planned_date_begin:
                ideal = task.planned_date_begin.date() if hasattr(task.planned_date_begin, 'date') else task.planned_date_begin
                task.overdue_days = max(0, (today - ideal).days)
            else:
                task.overdue_days = 0

    @api.depends('overdue_days')
    def _compute_is_route_magnet(self):
        ICP = self.env['ir.config_parameter'].sudo()
        threshold = int(ICP.get_param('route_optimization.critical_overdue_days', '14'))
        for task in self:
            task.is_route_magnet = task.overdue_days >= threshold
