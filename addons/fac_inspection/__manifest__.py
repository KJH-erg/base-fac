{
    'name': 'FAC Quality Inspection',
    'version': '20.0.2.0.0',
    'summary': 'Inspect against spec limits, judge pass/fail, raise NCRs',
    'category': 'Manufacturing/FAC',
    'depends': ['base'],
    'data': [
        'security/ir.access.csv',
        'data/ir_sequence_data.xml',
        'views/fac_inspection_spec_views.xml',
        'views/fac_inspection_views.xml',
        'views/fac_inspection_ncr_views.xml',
        'views/fac_inspection_menus.xml',
    ],
    'demo': [
        'demo/fac_inspection_demo.xml',
    ],
    'application': True,
    'author': 'DGIST AI4SE Lab',
    'license': 'LGPL-3',
}
