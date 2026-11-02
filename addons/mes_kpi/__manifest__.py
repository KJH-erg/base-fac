{
    'name': 'MES KPI Dashboard',
    'version': '20.0.1.0.0',
    'summary': 'OEE, plan achievement, defect rate and downtime by line and period',
    'category': 'Manufacturing',
    'author': 'Your Name',
    'license': 'LGPL-3',
    'depends': ['mes_production_result'],
    'data': [
        'security/ir.access.csv',
        'views/mes_kpi_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mes_kpi/static/src/**/*',
        ],
    },
}
