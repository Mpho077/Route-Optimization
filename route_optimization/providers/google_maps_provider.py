import logging
import requests

from .base_provider import BaseRoutingProvider, RoutingProviderError

_logger = logging.getLogger(__name__)

GOOGLE_MAPS_BASE = 'https://maps.googleapis.com/maps/api'


class GoogleMapsProvider(BaseRoutingProvider):
    """Google Maps Platform provider.

    Requires a valid API key with these APIs enabled:
        - Distance Matrix API
        - Directions API
        - Geocoding API
    """

    PROVIDER_NAME = 'google_maps'

    def __init__(self, config):
        config.setdefault('base_url', GOOGLE_MAPS_BASE)
        super().__init__(config)
        if not self.api_key:
            _logger.warning("GoogleMapsProvider initialised without an API key.")

    # ------------------------------------------------------------------
    # Distance / Time Matrix
    # ------------------------------------------------------------------
    def get_distance_matrix(self, coordinates):
        coords = self._format_coordinates(coordinates)

        # Google expects "lat,lng" (note: reversed vs OSRM)
        origins = '|'.join(f'{lat},{lng}' for lng, lat in coords)
        destinations = origins  # NxN matrix

        url = f'{self.base_url}/distancematrix/json'
        params = {
            'origins': origins,
            'destinations': destinations,
            'mode': 'driving',
            'key': self.api_key,
        }

        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise RoutingProviderError(
                f"Distance Matrix request failed: {exc}",
                provider=self.PROVIDER_NAME,
            ) from exc

        if data.get('status') != 'OK':
            raise RoutingProviderError(
                f"Google API error: {data.get('status')} — {data.get('error_message', '')}",
                provider=self.PROVIDER_NAME,
                response=data,
            )

        durations = []
        distances = []
        for row in data['rows']:
            dur_row = []
            dist_row = []
            for element in row['elements']:
                if element['status'] != 'OK':
                    dur_row.append(None)
                    dist_row.append(None)
                else:
                    dur_row.append(element['duration']['value'])      # seconds
                    dist_row.append(element['distance']['value'])     # meters
            durations.append(dur_row)
            distances.append(dist_row)

        return {
            'durations': durations,
            'distances': distances,
        }

    # ------------------------------------------------------------------
    # Single Route / Directions
    # ------------------------------------------------------------------
    def get_route(self, coordinates):
        coords = self._format_coordinates(coordinates)

        origin = f'{coords[0][1]},{coords[0][0]}'        # lat,lng
        destination = f'{coords[-1][1]},{coords[-1][0]}'
        waypoints = '|'.join(
            f'{lat},{lng}' for lng, lat in coords[1:-1]
        ) if len(coords) > 2 else ''

        url = f'{self.base_url}/directions/json'
        params = {
            'origin': origin,
            'destination': destination,
            'mode': 'driving',
            'key': self.api_key,
        }
        if waypoints:
            params['waypoints'] = waypoints

        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise RoutingProviderError(
                f"Directions request failed: {exc}",
                provider=self.PROVIDER_NAME,
            ) from exc

        if data.get('status') != 'OK':
            raise RoutingProviderError(
                f"Google API error: {data.get('status')} — {data.get('error_message', '')}",
                provider=self.PROVIDER_NAME,
                response=data,
            )

        route = data['routes'][0]
        total_duration = sum(leg['duration']['value'] for leg in route['legs'])
        total_distance = sum(leg['distance']['value'] for leg in route['legs'])

        return {
            'total_duration': total_duration,
            'total_distance': total_distance,
            'geometry': route['overview_polyline']['points'],
            'legs': [
                {
                    'duration': leg['duration']['value'],
                    'distance': leg['distance']['value'],
                }
                for leg in route['legs']
            ],
        }

    # ------------------------------------------------------------------
    # Geocoding
    # ------------------------------------------------------------------
    def geocode(self, address):
        url = f'{self.base_url}/geocode/json'
        params = {
            'address': address,
            'key': self.api_key,
        }

        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise RoutingProviderError(
                f"Geocode request failed: {exc}",
                provider=self.PROVIDER_NAME,
            ) from exc

        if data.get('status') != 'OK' or not data.get('results'):
            return None

        hit = data['results'][0]
        loc = hit['geometry']['location']
        return {
            'lat': loc['lat'],
            'lng': loc['lng'],
            'formatted_address': hit.get('formatted_address', ''),
        }

    # ------------------------------------------------------------------
    # Reverse Geocoding
    # ------------------------------------------------------------------
    def reverse_geocode(self, lat, lng):
        url = f'{self.base_url}/geocode/json'
        params = {
            'latlng': f'{lat},{lng}',
            'key': self.api_key,
        }

        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise RoutingProviderError(
                f"Reverse geocode request failed: {exc}",
                provider=self.PROVIDER_NAME,
            ) from exc

        if data.get('status') != 'OK' or not data.get('results'):
            return None

        hit = data['results'][0]
        components = {}
        for comp in hit.get('address_components', []):
            for t in comp.get('types', []):
                components[t] = comp['long_name']

        return {
            'formatted_address': hit.get('formatted_address', ''),
            'components': components,
        }

    # ------------------------------------------------------------------
    # Health Check
    # ------------------------------------------------------------------
    def test_connection(self):
        if not self.api_key:
            return {
                'status': 'error',
                'message': 'No API key configured.',
                'provider': self.PROVIDER_NAME,
            }
        try:
            url = f'{self.base_url}/geocode/json'
            params = {
                'address': 'Oslo, Norway',
                'key': self.api_key,
            }
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()

            api_status = data.get('status', 'UNKNOWN')
            error_msg = data.get('error_message', '')

            if api_status == 'OK' and data.get('results'):
                return {
                    'status': 'ok',
                    'message': 'Google Maps API is reachable and key is valid.',
                    'provider': self.PROVIDER_NAME,
                }
            return {
                'status': 'error',
                'message': f'Google API status: {api_status}. {error_msg}'.strip(),
                'provider': self.PROVIDER_NAME,
            }
        except requests.RequestException as exc:
            return {
                'status': 'error',
                'message': f'Request failed: {exc}',
                'provider': self.PROVIDER_NAME,
            }
