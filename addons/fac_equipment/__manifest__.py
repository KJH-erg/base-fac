{
    'name': 'FAC Equipment',
    'version': '20.0.2.0.0',
    'summary': 'Register equipment and track its status history',
    'category': 'Manufacturing/FAC',
    'depends': ['base'],
    'data': [
        'security/ir.access.csv',
        'views/fac_equipment_views.xml',
        'views/fac_equipment_status_log_views.xml',
        'views/fac_equipment_menus.xml',
    ],
    'demo': [
        'demo/fac_equipment_demo.xml',
    ],
    'application': True,
    'author': 'DGIST AI4SE Lab',
    'license': 'LGPL-3',
}
