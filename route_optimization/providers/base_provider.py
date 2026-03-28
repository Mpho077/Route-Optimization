import abc
import logging

_logger = logging.getLogger(__name__)


class BaseRoutingProvider(abc.ABC):
    """Abstract base class for all routing providers.

    Every provider must implement these methods. The optimizer engine
    calls only these interfaces, so adding a new provider (e.g. Mapbox,
    HERE, Valhalla) requires only a new subclass — zero changes to the
    optimizer or Odoo models.
    """

    def __init__(self, config):
        """
        Args:
            config (dict): Provider-specific configuration.
                Common keys:
                    - 'base_url': str — API endpoint or self-hosted URL
                    - 'api_key': str — API key (empty for keyless providers like OSRM)
                    - 'timeout': int — request timeout in seconds
        """
        self.base_url = config.get('base_url', '')
        self.api_key = config.get('api_key', '')
        self.timeout = config.get('timeout', 30)

    # ------------------------------------------------------------------
    # Distance / Time Matrix
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def get_distance_matrix(self, coordinates):
        """Return an NxN matrix of travel times (seconds) between all points.

        Args:
            coordinates (list[tuple[float, float]]): List of (lng, lat) pairs.
                Index 0 is typically the depot/start location.

        Returns:
            dict: {
                'durations': list[list[float]],   # NxN seconds
                'distances': list[list[float]],   # NxN meters
            }

        Raises:
            RoutingProviderError: On network or API errors.
        """

    # ------------------------------------------------------------------
    # Single Route / Directions
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def get_route(self, coordinates):
        """Return the driving route through an ordered list of waypoints.

        Args:
            coordinates (list[tuple[float, float]]): Ordered (lng, lat) pairs.

        Returns:
            dict: {
                'total_duration': float,      # seconds
                'total_distance': float,      # meters
                'geometry': str or dict,      # encoded polyline or GeoJSON
                'legs': list[dict],           # per-leg duration/distance
            }

        Raises:
            RoutingProviderError: On network or API errors.
        """

    # ------------------------------------------------------------------
    # Geocoding (address -> coordinates)
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def geocode(self, address):
        """Convert a street address to coordinates.

        Args:
            address (str): Full street address.

        Returns:
            dict: {
                'lat': float,
                'lng': float,
                'formatted_address': str,
            }
            Returns None if no result found.

        Raises:
            RoutingProviderError: On network or API errors.
        """

    # ------------------------------------------------------------------
    # Reverse Geocoding (coordinates -> address)
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def reverse_geocode(self, lat, lng):
        """Convert coordinates to a street address.

        Args:
            lat (float): Latitude.
            lng (float): Longitude.

        Returns:
            dict: {
                'formatted_address': str,
                'components': dict,
            }
            Returns None if no result found.

        Raises:
            RoutingProviderError: On network or API errors.
        """

    # ------------------------------------------------------------------
    # Health Check
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def test_connection(self):
        """Verify the provider is reachable and credentials are valid.

        Returns:
            dict: {
                'status': 'ok' | 'error',
                'message': str,
                'provider': str,
            }
        """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _format_coordinates(self, coordinates):
        """Validate and normalize coordinate list.

        Args:
            coordinates: list of (lng, lat) tuples.

        Returns:
            list[tuple[float, float]]: Validated coordinates.

        Raises:
            ValueError: If coordinates are invalid.
        """
        if not coordinates or len(coordinates) < 2:
            raise ValueError("At least 2 coordinates are required.")
        validated = []
        for coord in coordinates:
            if len(coord) != 2:
                raise ValueError(f"Invalid coordinate: {coord}")
            lng, lat = float(coord[0]), float(coord[1])
            if not (-180 <= lng <= 180 and -90 <= lat <= 90):
                raise ValueError(f"Coordinate out of range: lng={lng}, lat={lat}")
            validated.append((lng, lat))
        return validated


class RoutingProviderError(Exception):
    """Raised when a routing provider encounters an error."""

    def __init__(self, message, provider=None, response=None):
        self.provider = provider
        self.response = response
        super().__init__(f"[{provider}] {message}" if provider else message)
