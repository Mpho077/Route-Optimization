from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # --- Google Maps Configuration ---
    google_maps_api_key = fields.Char(
        string='Google Maps API Key',
        config_parameter='route_optimization.google_maps_api_key',
        help='API key with Distance Matrix, Directions, and Geocoding APIs enabled.',
    )
    google_maps_base_url = fields.Char(
        string='Google Maps API Base URL',
        default='https://maps.googleapis.com/maps/api',
        config_parameter='route_optimization.google_maps_base_url',
    )

    # --- General Settings ---
    request_timeout = fields.Integer(
        string='Request Timeout (seconds)',
        default=30,
        config_parameter='route_optimization.request_timeout',
    )

    # --- Optimization Weights ---
    distance_penalty_per_km = fields.Float(
        string='Distance Penalty / km',
        default=2.0,
        config_parameter='route_optimization.distance_penalty_per_km',
        help='Points deducted from route score per km of driving.',
    )
    overdue_base = fields.Float(
        string='Overdue Exponent Base',
        default=1.5,
        config_parameter='route_optimization.overdue_base',
        help='Exponential base for the overdue urgency multiplier.',
    )
    overdue_multiplier = fields.Float(
        string='Overdue Multiplier',
        default=10.0,
        config_parameter='route_optimization.overdue_multiplier',
        help='Multiplier applied to the exponential overdue term.',
    )
    critical_overdue_days = fields.Integer(
        string='Critical Overdue Threshold (days)',
        default=14,
        config_parameter='route_optimization.critical_overdue_days',
        help='Days overdue before a job becomes a mandatory "magnet" anchor.',
    )
    cluster_bonus = fields.Float(
        string='Same-ZIP Cluster Bonus',
        default=5.0,
        config_parameter='route_optimization.cluster_bonus',
        help='Bonus points for visiting tasks in the same postal code.',
    )

    def action_test_connection(self):
        """Test button to verify the Google Maps API connection."""
        from ..providers.provider_factory import get_routing_provider
        try:
            provider = get_routing_provider(self.env)
            result = provider.test_connection()
            if result['status'] == 'ok':
                message = f"Connection successful: {result['message']}"
                msg_type = 'success'
            else:
                message = f"Connection failed: {result['message']}"
                msg_type = 'warning'
        except Exception as exc:
            message = f"Error: {exc}"
            msg_type = 'danger'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Google Maps Connection Test',
                'message': message,
                'type': msg_type,
                'sticky': False,
            },
        }
