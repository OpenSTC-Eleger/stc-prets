# -*- coding: utf-8 -*-

##############################################################################
#    Copyright (C) 2012 SICLIC http://siclic.fr
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>
#
#############################################################################

{
    "name": "OpenResa",
    "version": "1.0",
    "depends": ['web','web_calendar','base','openbase','purchase','stock','hotel','hotel_reservation','email_template'],
    "author": "SICLIC",
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
        'views/openresa_data.xml',
        'security/ir.model.access.csv',
        'security/openresa_security.xml',
        "wizard/openresa_view_wizard.xml",

        "views/openresa_checkout_view.xml",
        "views/openresa_view.xml",
        'views/openresa_menus_view.xml',
        'views/openresa_report.xml',

        "workflow/openresa_workflow.xml",
        'workflow/purchase_workflow.xml',
        "test/cr_commit.yml", "test/openresa_tests_data.xml","test/openresa_core.yml", "test/openresa_bookable.yml", "test/rollback_tests.yml",

        ],
    "js":['static/src/js/calendar_inherit.js'],
    "demo": [],
    "test": [],
    "installable": True,
    "active": False,
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
