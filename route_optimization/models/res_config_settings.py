from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # --- Provider Selection ---
    routing_provider = fields.Selection(
        [
            ('osrm', 'OSRM (Self-hosted, Free)'),
            ('google_maps', 'Google Maps Platform'),
        ],
        string='Routing Provider',
        default='osrm',
        config_parameter='route_optimization.routing_provider',
    )
    geocoding_provider = fields.Selection(
        [
            ('osrm', 'Nominatim / OSM (Free)'),
            ('google_maps', 'Google Maps Geocoding'),
        ],
        string='Geocoding Provider',
        default='osrm',
        config_parameter='route_optimization.geocoding_provider',
        help='Can differ from routing provider. E.g. use Google for geocoding '
             'and OSRM for routing.',
    )

    # --- OSRM Configuration ---
    osrm_base_url = fields.Char(
        string='OSRM Base URL',
        default='http://localhost:5000',
        config_parameter='route_optimization.osrm_base_url',
        help='URL of the self-hosted OSRM backend (e.g. http://localhost:5000).',
    )

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

    def action_test_routing_provider(self):
        """Test button to verify the selected routing provider connection."""
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
                'title': 'Routing Provider Test',
                'message': message,
                'type': msg_type,
                'sticky': False,
            },
        }

    def action_test_geocoding_provider(self):
        """Test button to verify the selected geocoding provider connection."""
        from ..providers.provider_factory import get_geocoding_provider
        try:
            provider = get_geocoding_provider(self.env)
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
                'title': 'Geocoding Provider Test',
                'message': message,
                'type': msg_type,
                'sticky': False,
            },
        }
