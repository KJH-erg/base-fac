{
    'name': 'MES Routing',
    'version': '20.0.1.0.0',
    'summary': 'Reusable process routes with steps, lines and standard times',
    'category': 'Manufacturing',
    'author': 'Your Name',
    'license': 'LGPL-3',
    'depends': ['mrp'],
    'data': [
        'security/ir.access.csv',
        'views/mes_menus.xml',
        'views/mes_routing_views.xml',
    ],
    'application': True,
}
