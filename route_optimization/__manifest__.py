{
    'name': 'Route Optimization',
    'version': '19.0.1.0.0',
    'category': 'Field Service',
    'summary': 'Automated daily route optimization for field service technicians',
    'description': """
        Route Optimization Module for Pest Control Field Service
        =========================================================
        - Multi-provider routing support (OSRM, Google Maps)
        - SLA-weighted job prioritization with overdue multiplier
        - Daily cron-based route generation per technician
        - Visual map widget with Leaflet.js / OpenStreetMap
        - Configurable weighting engine for balancing drive time vs urgency
    """,
    'author': 'Custom',
    'website': '',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'industry_fsm',
        'hr',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/res_config_settings_views.xml',
        'views/project_task_views.xml',
        'views/route_plan_views.xml',
        'views/route_map_template.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'route_optimization/static/src/js/route_map_widget.js',
            'route_optimization/static/src/xml/route_map_widget.xml',
            'route_optimization/static/src/css/route_map.css',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
