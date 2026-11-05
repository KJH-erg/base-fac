{
    'name': 'FAC Maintenance',
    'version': '20.0.2.0.0',
    'summary': 'Maintenance requests from request to done, with cost and history',
    'category': 'Manufacturing/FAC',
    'depends': ['base'],
    'data': [
        'security/ir.access.csv',
        'data/ir_sequence_data.xml',
        'views/fac_maintenance_request_views.xml',
        'views/fac_maintenance_menus.xml',
    ],
    'demo': [
        'demo/fac_maintenance_demo.xml',
    ],
    'application': True,
    'author': 'DGIST AI4SE Lab',
    'license': 'LGPL-3',
}
