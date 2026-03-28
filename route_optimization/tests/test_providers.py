"""Tests for routing providers — OSRM and Google Maps.

These tests mock HTTP calls so they run without any external services.
Run with:  python -m pytest tests/test_providers.py -v
  or via:  odoo-bin -d testdb --test-tags route_optimization -i route_optimization
"""
from unittest.mock import patch, MagicMock
from odoo.tests.common import TransactionCase, tagged


# ---------------------------------------------------------------------------
# Helper: build a mock requests.get response
# ---------------------------------------------------------------------------
def _mock_response(json_data, status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data
    mock.raise_for_status.return_value = None
    return mock


@tagged('post_install', '-at_install', 'route_optimization')
class TestOSRMProvider(TransactionCase):
    """Test the OSRM provider with mocked HTTP responses."""

    def setUp(self):
        super().setUp()
        from ..providers.osrm_provider import OSRMProvider
        self.provider = OSRMProvider({
            'base_url': 'http://test-osrm:5000',
            'timeout': 5,
        })

    # -- Distance Matrix --------------------------------------------------
    @patch('odoo.addons.route_optimization.providers.osrm_provider.requests.get')
    def test_distance_matrix_success(self, mock_get):
        """OSRM /table returns valid NxN matrix."""
        mock_get.return_value = _mock_response({
            'code': 'Ok',
            'durations': [
                [0, 120.5, 250.3],
                [115.2, 0, 180.1],
                [245.0, 175.8, 0],
            ],
            'distances': [
                [0, 2000, 5000],
                [1900, 0, 3500],
                [4800, 3400, 0],
            ],
        })

        coords = [(10.75, 59.91), (10.80, 59.92), (10.85, 59.90)]
        result = self.provider.get_distance_matrix(coords)

        self.assertEqual(len(result['durations']), 3)
        self.assertEqual(len(result['durations'][0]), 3)
        self.assertEqual(result['durations'][0][0], 0)
        self.assertGreater(result['durations'][0][1], 0)

        # Verify the URL was called correctly
        call_url = mock_get.call_args[0][0]
        self.assertIn('/table/v1/driving/', call_url)
        self.assertIn('10.75,59.91', call_url)

    @patch('odoo.addons.route_optimization.providers.osrm_provider.requests.get')
    def test_distance_matrix_error(self, mock_get):
        """OSRM returns an error code — should raise RoutingProviderError."""
        mock_get.return_value = _mock_response({
            'code': 'InvalidQuery',
            'message': 'Could not find a route',
        })

        from ..providers.base_provider import RoutingProviderError
        with self.assertRaises(RoutingProviderError):
            self.provider.get_distance_matrix([(10.75, 59.91), (10.80, 59.92)])

    # -- Route / Directions ------------------------------------------------
    @patch('odoo.addons.route_optimization.providers.osrm_provider.requests.get')
    def test_get_route_success(self, mock_get):
        """OSRM /route returns route with geometry."""
        mock_get.return_value = _mock_response({
            'code': 'Ok',
            'routes': [{
                'duration': 600.0,
                'distance': 8500.0,
                'geometry': {
                    'type': 'LineString',
                    'coordinates': [[10.75, 59.91], [10.80, 59.92]],
                },
                'legs': [
                    {'duration': 600.0, 'distance': 8500.0},
                ],
            }],
        })

        result = self.provider.get_route([(10.75, 59.91), (10.80, 59.92)])
        self.assertEqual(result['total_duration'], 600.0)
        self.assertEqual(result['total_distance'], 8500.0)
        self.assertIn('geometry', result)
        self.assertEqual(len(result['legs']), 1)

    # -- Geocoding (Nominatim) --------------------------------------------
    @patch('odoo.addons.route_optimization.providers.osrm_provider.requests.get')
    def test_geocode_success(self, mock_get):
        """Nominatim returns a geocoding result."""
        mock_get.return_value = _mock_response([{
            'lat': '59.9139',
            'lon': '10.7522',
            'display_name': 'Oslo, Norway',
        }])

        result = self.provider.geocode('Oslo, Norway')
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result['lat'], 59.9139, places=3)
        self.assertAlmostEqual(result['lng'], 10.7522, places=3)

    @patch('odoo.addons.route_optimization.providers.osrm_provider.requests.get')
    def test_geocode_no_results(self, mock_get):
        """Nominatim returns empty results — should return None."""
        mock_get.return_value = _mock_response([])
        result = self.provider.geocode('zzznonexistent999')
        self.assertIsNone(result)

    # -- Health Check ------------------------------------------------------
    @patch('odoo.addons.route_optimization.providers.osrm_provider.requests.get')
    def test_connection_ok(self, mock_get):
        """OSRM /nearest responds OK."""
        mock_get.return_value = _mock_response({'code': 'Ok'})
        result = self.provider.test_connection()
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['provider'], 'osrm')

    @patch('odoo.addons.route_optimization.providers.osrm_provider.requests.get')
    def test_connection_fail(self, mock_get):
        """OSRM unreachable — should return error status."""
        import requests as req_lib
        mock_get.side_effect = req_lib.ConnectionError("Connection refused")
        result = self.provider.test_connection()
        self.assertEqual(result['status'], 'error')

    # -- Coordinate Validation ---------------------------------------------
    def test_invalid_coordinates_too_few(self):
        """Less than 2 coordinates should raise ValueError."""
        with self.assertRaises(ValueError):
            self.provider._format_coordinates([(10.75, 59.91)])

    def test_invalid_coordinates_out_of_range(self):
        """Coordinates outside valid range should raise ValueError."""
        with self.assertRaises(ValueError):
            self.provider._format_coordinates([(999, 59.91), (10.80, 59.92)])


@tagged('post_install', '-at_install', 'route_optimization')
class TestGoogleMapsProvider(TransactionCase):
    """Test the Google Maps provider with mocked HTTP responses."""

    def setUp(self):
        super().setUp()
        from ..providers.google_maps_provider import GoogleMapsProvider
        self.provider = GoogleMapsProvider({
            'base_url': 'https://maps.googleapis.com/maps/api',
            'api_key': 'TEST_KEY_NOT_REAL',
            'timeout': 5,
        })

    # -- Distance Matrix ---------------------------------------------------
    @patch('odoo.addons.route_optimization.providers.google_maps_provider.requests.get')
    def test_distance_matrix_success(self, mock_get):
        """Google Distance Matrix returns valid NxN data."""
        mock_get.return_value = _mock_response({
            'status': 'OK',
            'rows': [
                {'elements': [
                    {'status': 'OK', 'duration': {'value': 0}, 'distance': {'value': 0}},
                    {'status': 'OK', 'duration': {'value': 300}, 'distance': {'value': 4000}},
                ]},
                {'elements': [
                    {'status': 'OK', 'duration': {'value': 310}, 'distance': {'value': 4100}},
                    {'status': 'OK', 'duration': {'value': 0}, 'distance': {'value': 0}},
                ]},
            ],
        })

        result = self.provider.get_distance_matrix([(10.75, 59.91), (10.80, 59.92)])
        self.assertEqual(len(result['durations']), 2)
        self.assertEqual(result['durations'][0][1], 300)
        self.assertEqual(result['distances'][0][1], 4000)

        # Verify API key was passed
        call_kwargs = mock_get.call_args
        self.assertIn('TEST_KEY_NOT_REAL', str(call_kwargs))

    @patch('odoo.addons.route_optimization.providers.google_maps_provider.requests.get')
    def test_distance_matrix_api_error(self, mock_get):
        """Google returns REQUEST_DENIED — should raise RoutingProviderError."""
        mock_get.return_value = _mock_response({
            'status': 'REQUEST_DENIED',
            'error_message': 'API key invalid',
        })

        from ..providers.base_provider import RoutingProviderError
        with self.assertRaises(RoutingProviderError):
            self.provider.get_distance_matrix([(10.75, 59.91), (10.80, 59.92)])

    # -- Route / Directions ------------------------------------------------
    @patch('odoo.addons.route_optimization.providers.google_maps_provider.requests.get')
    def test_get_route_success(self, mock_get):
        """Google Directions returns route with polyline."""
        mock_get.return_value = _mock_response({
            'status': 'OK',
            'routes': [{
                'overview_polyline': {'points': 'encodedPolylineString'},
                'legs': [
                    {'duration': {'value': 420}, 'distance': {'value': 6200}},
                    {'duration': {'value': 300}, 'distance': {'value': 3800}},
                ],
            }],
        })

        coords = [(10.75, 59.91), (10.80, 59.92), (10.85, 59.90)]
        result = self.provider.get_route(coords)
        self.assertEqual(result['total_duration'], 720)
        self.assertEqual(result['total_distance'], 10000)
        self.assertEqual(len(result['legs']), 2)

    # -- Geocoding ---------------------------------------------------------
    @patch('odoo.addons.route_optimization.providers.google_maps_provider.requests.get')
    def test_geocode_success(self, mock_get):
        """Google Geocoding returns a result."""
        mock_get.return_value = _mock_response({
            'status': 'OK',
            'results': [{
                'geometry': {'location': {'lat': 59.9139, 'lng': 10.7522}},
                'formatted_address': 'Oslo, Norway',
            }],
        })

        result = self.provider.geocode('Oslo, Norway')
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result['lat'], 59.9139, places=3)

    # -- Health Check (no key) ---------------------------------------------
    def test_connection_no_key(self):
        """Provider without API key should return error."""
        from ..providers.google_maps_provider import GoogleMapsProvider
        no_key_provider = GoogleMapsProvider({'base_url': 'https://maps.googleapis.com/maps/api'})
        result = no_key_provider.test_connection()
        self.assertEqual(result['status'], 'error')
        self.assertIn('No API key', result['message'])


@tagged('post_install', '-at_install', 'route_optimization')
class TestProviderFactory(TransactionCase):
    """Test the provider factory reads config and returns correct providers."""

    def test_default_provider_is_osrm(self):
        """With no config set, factory should default to OSRM."""
        from ..providers.provider_factory import get_routing_provider
        from ..providers.osrm_provider import OSRMProvider
        provider = get_routing_provider(self.env)
        self.assertIsInstance(provider, OSRMProvider)

    def test_switch_to_google_maps(self):
        """Setting config to google_maps should return GoogleMapsProvider."""
        from ..providers.provider_factory import get_routing_provider
        from ..providers.google_maps_provider import GoogleMapsProvider

        self.env['ir.config_parameter'].sudo().set_param(
            'route_optimization.routing_provider', 'google_maps'
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'route_optimization.google_maps_api_key', 'TEST_KEY'
        )
        provider = get_routing_provider(self.env)
        self.assertIsInstance(provider, GoogleMapsProvider)

    def test_unknown_provider_raises(self):
        """Unknown provider key should raise RoutingProviderError."""
        from ..providers.provider_factory import get_routing_provider
        from ..providers.base_provider import RoutingProviderError

        self.env['ir.config_parameter'].sudo().set_param(
            'route_optimization.routing_provider', 'nonexistent'
        )
        with self.assertRaises(RoutingProviderError):
            get_routing_provider(self.env)

    def test_separate_geocoding_provider(self):
        """Routing=OSRM, Geocoding=Google should return different instances."""
        from ..providers.provider_factory import get_routing_provider, get_geocoding_provider
        from ..providers.osrm_provider import OSRMProvider
        from ..providers.google_maps_provider import GoogleMapsProvider

        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('route_optimization.routing_provider', 'osrm')
        ICP.set_param('route_optimization.geocoding_provider', 'google_maps')
        ICP.set_param('route_optimization.google_maps_api_key', 'TEST_KEY')

        routing = get_routing_provider(self.env)
        geocoding = get_geocoding_provider(self.env)

        self.assertIsInstance(routing, OSRMProvider)
        self.assertIsInstance(geocoding, GoogleMapsProvider)
