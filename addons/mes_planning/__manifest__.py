{
    'name': 'MES Production Planning',
    'version': '20.0.1.0.0',
    'summary': 'Daily production plans with line load and deadline checks',
    'category': 'Manufacturing',
    'author': 'Your Name',
    'license': 'LGPL-3',
    'depends': ['mes_routing'],
    'data': [
        'security/ir.access.csv',
        'data/ir_sequence_data.xml',
        'views/mes_production_plan_views.xml',
    ],
}
