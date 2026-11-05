{
    'name': 'FAC Materials',
    'version': '20.0.2.0.0',
    'summary': 'Register materials, receive and issue stock, warn below minimum',
    'category': 'Manufacturing/FAC',
    'depends': ['base'],
    'data': [
        'security/ir.access.csv',
        'data/ir_sequence_data.xml',
        'views/fac_material_views.xml',
        'views/fac_material_move_views.xml',
        'views/fac_material_menus.xml',
    ],
    'demo': [
        'demo/fac_material_demo.xml',
    ],
    'application': True,
    'author': 'DGIST AI4SE Lab',
    'license': 'LGPL-3',
}
