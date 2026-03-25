import logging
import requests

from .base_provider import BaseRoutingProvider, RoutingProviderError

_logger = logging.getLogger(__name__)

DEFAULT_OSRM_URL = 'http://localhost:5000'


class OSRMProvider(BaseRoutingProvider):
    """Open Source Routing Machine — self-hosted, zero-cost provider.

    Expects a running OSRM backend (Docker or native).
    No API key required.
    """

    PROVIDER_NAME = 'osrm'

    def __init__(self, config):
        config.setdefault('base_url', DEFAULT_OSRM_URL)
        super().__init__(config)

    # ------------------------------------------------------------------
    # Distance / Time Matrix
    # ------------------------------------------------------------------
    def get_distance_matrix(self, coordinates):
        coords = self._format_coordinates(coordinates)
        coords_str = ';'.join(f'{lng},{lat}' for lng, lat in coords)
        url = f'{self.base_url}/table/v1/driving/{coords_str}'
        params = {'annotations': 'duration,distance'}

        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise RoutingProviderError(
                f"Matrix request failed: {exc}",
                provider=self.PROVIDER_NAME,
            ) from exc

        if data.get('code') != 'Ok':
            raise RoutingProviderError(
                f"OSRM error: {data.get('message', data.get('code'))}",
                provider=self.PROVIDER_NAME,
                response=data,
            )

        return {
            'durations': data['durations'],
            'distances': data.get('distances', []),
        }

    # ------------------------------------------------------------------
    # Single Route / Directions
    # ------------------------------------------------------------------
    def get_route(self, coordinates):
        coords = self._format_coordinates(coordinates)
        coords_str = ';'.join(f'{lng},{lat}' for lng, lat in coords)
        url = f'{self.base_url}/route/v1/driving/{coords_str}'
        params = {
            'overview': 'full',
            'geometries': 'geojson',
            'steps': 'false',
        }

        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise RoutingProviderError(
                f"Route request failed: {exc}",
                provider=self.PROVIDER_NAME,
            ) from exc

        if data.get('code') != 'Ok':
            raise RoutingProviderError(
                f"OSRM error: {data.get('message', data.get('code'))}",
                provider=self.PROVIDER_NAME,
                response=data,
            )

        route = data['routes'][0]
        return {
            'total_duration': route['duration'],
            'total_distance': route['distance'],
            'geometry': route['geometry'],
            'legs': [
                {
                    'duration': leg['duration'],
                    'distance': leg['distance'],
                }
                for leg in route['legs']
            ],
        }

    # ------------------------------------------------------------------
    # Geocoding — OSRM does not support geocoding natively.
    # Delegates to Nominatim (free, no key).
    # ------------------------------------------------------------------
    def geocode(self, address):
        url = 'https://nominatim.openstreetmap.org/search'
        params = {
            'q': address,
            'format': 'jsonv2',
            'limit': 1,
            'addressdetails': 1,
        }
        headers = {'User-Agent': 'OdooRouteOptimization/1.0'}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            results = resp.json()
        except requests.RequestException as exc:
            raise RoutingProviderError(
                f"Nominatim geocode failed: {exc}",
                provider=self.PROVIDER_NAME,
            ) from exc

        if not results:
            return None

        hit = results[0]
        return {
            'lat': float(hit['lat']),
            'lng': float(hit['lon']),
            'formatted_address': hit.get('display_name', ''),
        }

    # ------------------------------------------------------------------
    # Reverse Geocoding — via Nominatim
    # ------------------------------------------------------------------
    def reverse_geocode(self, lat, lng):
        url = 'https://nominatim.openstreetmap.org/reverse'
        params = {
            'lat': lat,
            'lon': lng,
            'format': 'jsonv2',
            'addressdetails': 1,
        }
        headers = {'User-Agent': 'OdooRouteOptimization/1.0'}

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise RoutingProviderError(
                f"Nominatim reverse geocode failed: {exc}",
                provider=self.PROVIDER_NAME,
            ) from exc

        if data.get('error'):
            return None

        return {
            'formatted_address': data.get('display_name', ''),
            'components': data.get('address', {}),
        }

    # ------------------------------------------------------------------
    # Health Check
    # ------------------------------------------------------------------
    def test_connection(self):
        try:
            # Simple nearest query to verify OSRM is alive
            url = f'{self.base_url}/nearest/v1/driving/13.388860,52.517037'
            resp = requests.get(url, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            if data.get('code') == 'Ok':
                return {
                    'status': 'ok',
                    'message': 'OSRM backend is reachable.',
                    'provider': self.PROVIDER_NAME,
                }
            return {
                'status': 'error',
                'message': f"Unexpected response: {data.get('code')}",
                'provider': self.PROVIDER_NAME,
            }
        except requests.RequestException as exc:
            return {
                'status': 'error',
                'message': str(exc),
                'provider': self.PROVIDER_NAME,
            }
