import logging

from .google_maps_provider import GoogleMapsProvider
from .base_provider import RoutingProviderError

_logger = logging.getLogger(__name__)


def get_routing_provider(env):
    """Instantiate the Google Maps routing provider from Odoo settings.

    Args:
        env: Odoo environment (``self.env``).

    Returns:
        GoogleMapsProvider: Configured provider instance.

    Raises:
        RoutingProviderError: If the API key is missing.
    """
    ICP = env['ir.config_parameter'].sudo()

    api_key = ICP.get_param('route_optimization.google_maps_api_key', '')
    if not api_key:
        raise RoutingProviderError(
            "Google Maps API key is not configured. "
            "Go to Settings > Route Optimization to set it.",
            provider='google_maps',
        )

    config = {
        'base_url': ICP.get_param(
            'route_optimization.google_maps_base_url',
            'https://maps.googleapis.com/maps/api',
        ),
        'api_key': api_key,
        'timeout': int(ICP.get_param('route_optimization.request_timeout', '30')),
    }

    _logger.info("Route optimization using Google Maps provider")
    return GoogleMapsProvider(config)


def get_geocoding_provider(env):
    """Return the Google Maps provider for geocoding.

    Args:
        env: Odoo environment.

    Returns:
        GoogleMapsProvider: Configured provider instance.
    """
    return get_routing_provider(env)
