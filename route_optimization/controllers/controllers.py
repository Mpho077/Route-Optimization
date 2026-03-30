import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class RouteMapController(http.Controller):

    @http.route('/route/map/<int:plan_id>', type='http', auth='user', website=False)
    def route_map_page(self, plan_id, **kwargs):
        """Full-page map view for a route plan (opens in new tab)."""
        plan = request.env['route.plan'].browse(plan_id)
        if not plan.exists():
            return request.not_found()

        map_data = plan.get_map_data()
        return request.render('route_optimization.route_map_page', {
            'route_data_json': json.dumps(map_data),
        })
