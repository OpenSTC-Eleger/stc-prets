# -*- coding: utf-8 -*-
##############################################################################
#
#   Openstc-oe
#
##############################################################################

{
    "name": "OpenResa",
    "version": "0.1",
    "depends": ['web','web_calendar','base','openbase','purchase','stock','hotel','email_template'],
    "author": "BP",
    "category": "SICLIC",
    "description": """
    Module de Gestion des Réservations (salles et équipements de la Mairie) auprès de particuliers / associations / professionnels.
    Il contient :
    * Gestion des demandes de Réservations (formulaire et calendrier)
    * Gestion des disponibilités des articles
    * Gestion des états des lieux après utilisation et récapitulatif des détériorations d'un article
    * Recensemement des demandeurs de réservations
    
    """,
    "data": [
        'security/ir.model.access.csv',
        'views/openstc_pret_data_resa.xml',
        
        "wizard/openstc_pret_view_wizard.xml",
        
        "views/openstc_pret_checkout_view.xml",
        "views/openstc_pret_view_resa.xml",
        'views/openstc_pret_menus_view.xml',
        

        "workflow/openstc_pret_workflow.xml",
        'workflow/purchase_workflow.xml',

        "test/cr_commit.yml", "test/openstc_prets_tests.yml",
        
        ],
    "js":['static/src/js/calendar_inherit.js'],
    "demo": [],
    "test": [],
    "installable": True,
    "active": False,
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
