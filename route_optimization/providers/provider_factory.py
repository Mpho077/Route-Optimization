import logging

from .osrm_provider import OSRMProvider
from .google_maps_provider import GoogleMapsProvider
from .base_provider import RoutingProviderError

_logger = logging.getLogger(__name__)

# Registry of available providers — add new ones here.
PROVIDER_REGISTRY = {
    'osrm': OSRMProvider,
    'google_maps': GoogleMapsProvider,
}


def get_routing_provider(env):
    """Instantiate the routing provider selected in Odoo settings.

    Reads configuration from ``res.config.settings`` via ``ir.config_parameter``
    and returns a ready-to-use provider instance.

    Args:
        env: Odoo environment (``self.env``).

    Returns:
        BaseRoutingProvider: Configured provider instance.

    Raises:
        RoutingProviderError: If the selected provider is unknown.
    """
    ICP = env['ir.config_parameter'].sudo()
    provider_key = ICP.get_param('route_optimization.routing_provider', 'osrm')

    cls = PROVIDER_REGISTRY.get(provider_key)
    if not cls:
        raise RoutingProviderError(
            f"Unknown routing provider: '{provider_key}'. "
            f"Available: {', '.join(PROVIDER_REGISTRY.keys())}",
        )

    config = {
        'base_url': ICP.get_param(f'route_optimization.{provider_key}_base_url', ''),
        'api_key': ICP.get_param(f'route_optimization.{provider_key}_api_key', ''),
        'timeout': int(ICP.get_param('route_optimization.request_timeout', '30')),
    }

    _logger.info("Route optimization using provider: %s", provider_key)
    return cls(config)


def get_geocoding_provider(env):
    """Instantiate the geocoding provider selected in Odoo settings.

    Geocoding can use a different provider from routing (e.g. Google for
    geocoding, OSRM for routing). Falls back to the routing provider if
    no separate geocoding provider is configured.

    Args:
        env: Odoo environment.

    Returns:
        BaseRoutingProvider: Provider instance with geocode() capability.
    """
    ICP = env['ir.config_parameter'].sudo()
    provider_key = ICP.get_param(
        'route_optimization.geocoding_provider',
        ICP.get_param('route_optimization.routing_provider', 'osrm'),
    )

    cls = PROVIDER_REGISTRY.get(provider_key)
    if not cls:
        raise RoutingProviderError(
            f"Unknown geocoding provider: '{provider_key}'. "
            f"Available: {', '.join(PROVIDER_REGISTRY.keys())}",
        )

    config = {
        'base_url': ICP.get_param(f'route_optimization.{provider_key}_base_url', ''),
        'api_key': ICP.get_param(f'route_optimization.{provider_key}_api_key', ''),
        'timeout': int(ICP.get_param('route_optimization.request_timeout', '30')),
    }

    return cls(config)
