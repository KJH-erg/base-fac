{
    'name': 'FAC Work Orders',
    'version': '20.0.2.0.0',
    'summary': 'Create work orders and move them from planned to done',
    'category': 'Manufacturing/FAC',
    'depends': ['base'],
    'data': [
        'security/ir.access.csv',
        'data/ir_sequence_data.xml',
        'views/fac_workorder_views.xml',
        'views/fac_workorder_menus.xml',
    ],
    'demo': [
        'demo/fac_workorder_demo.xml',
    ],
    'application': True,
    'author': 'DGIST AI4SE Lab',
    'license': 'LGPL-3',
}
