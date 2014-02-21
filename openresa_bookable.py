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
from openbase.openbase_core import OpenbaseCore
from osv import fields, osv

#----------------------------------------------------------
# Fournitures
#----------------------------------------------------------
class product_product(OpenbaseCore):


    AVAILABLE_ETATS = (("neuf", "Neuf"), ("bon", "Bon"), ("moyen", "Moyen"), ("mauvais", "Mauvais"), ("inutilisable", "Inutilisable"))

    _name = "product.product"
    _inherit = "product.product"
    _description = "Produit"


    _columns = {
        "etat": fields.selection(AVAILABLE_ETATS, "Etat"),
        "seuil_confirm":fields.integer("Qté Max sans Validation", help="Qté Maximale avant laquelle une étape de validation par un responsable est nécessaire"),
        "bloquant":fields.boolean("\"Non disponibilité\" bloquante", help="Un produit dont la non dispo est bloquante empêche la réservation de se poursuivre (elle reste en Brouillon)"),
        "empruntable":fields.boolean("Se fournir à l'extérieur", help="indique si l'on peut emprunter cette ressource à des collectivités extèrieures"),
        "checkout_lines":fields.one2many('openstc.pret.checkout.line', 'product_id', string="Lignes Etat des Lieux"),
        'need_infos_supp':fields.boolean('Nécessite Infos Supp ?', help="Indiquer si, pour une Réservation, cette ressource nécessite des infos supplémentaires A saisir par le demandeur."),
        'max_bookable_qty':fields.integer('Max Bookable qty', help='Qty max of this bookable authorized for one booking'),
        'openresa_property_manager_id': fields.property('res.users', type='many2one', relation='res.users', view_load=True, string='Gestionnaire'),
        }

    _defaults = {
        'seuil_confirm': 0,
        'need_infos_supp': lambda *a:0,
    }

    """
    @param claimer_user_id: the user who wants to reserve something
    @param claimer_partner_id: the partner who wants to reserve something
    @return: list of prod_ids reservable by user / partner
    @attention: may not work if both claimer_user_id and claimer_partner_id are supplied (raise Error)
    """
    def get_bookables(self, cr, uid, claimer_partner_id=False, context=None):
        prod_ids = []
        equipment_obj = self.pool.get("openstc.equipment")
        site_obj = self.pool.get("openstc.site")
        equipments = []
        sites = []
        domain = []
        partner_obj = self.pool.get('res.partner')
        service_obj = self.pool.get('openstc.service')
        if claimer_partner_id:
            partner = partner_obj.read(cr, uid, claimer_partner_id, ['is_department', 'type_id'], context=context)
            if partner['is_department']:
                service_id = service_obj.search(cr, uid, [('partner_id.id','=',claimer_partner_id)], context=context)
                if service_id:
                    domain = [('internal_booking','=',True),'|',
                              ('service_bookable_ids.id','child_of',service_id),
                              ('service_bookable_ids','=',False)]
            #else, if it's a partner, prod_ids are filtered according to 'external' reservable rights
            else:
                domain = [('external_booking','=',True),'|',
                          ('partner_type_bookable_ids.id','child_of',partner['type_id'] and partner['type_id'][0] or []),
                          ('partner_type_bookable_ids','=',False)]
        #else, if not any partner_id or user_id is supplied, returns all with no fitler
        else:
            domain = ['|',('internal_booking','=',True),('external_booking','=',True)]

        #retrieve values for equipments and sites authorized
        equipment_ids = equipment_obj.search(cr, uid, domain, context=context)
        equipments = equipment_obj.read(cr, uid, equipment_ids, ['product_product_id'], context=context)
        site_ids = site_obj.search(cr, uid, domain, context=context)
        sites = site_obj.read(cr, uid, site_ids, ['product_id'], context=context)

        #finally, compute results by merging 'product.product' many2ones of
        #records from tables openstc.equipment and openstc.site
        prod_ids.extend([elt['product_product_id'][0] for elt in equipments if elt['product_product_id']])
        prod_ids.extend([elt['product_id'][0] for elt in sites if elt['product_id']])
        return prod_ids

        """
    @param prod_id: product_id from which to compute new uom
    @param length: length of resa (in hours)
    @return: new_uom_qty to apply for invoicing
    @note: if product uom refers to a resa time (checked by categ_uom xml_id),
    we use it to perform compute
    else, use uom_day to perform compute
    """
    def get_temporal_uom_qty(self, cr, uid, prod_id, length, context=None):
        record = self.pool.get('product.product').browse(cr, uid, prod_id, context=context)
        uom_obj = self.pool.get('product.uom')
        data_obj = self.pool.get('ir.model.data')
        #@TOCHECK: must i check user deletion of those uom (avoid crash if data are missing) ?
        hour_uom_id = data_obj.get_object_reference(cr, uid, 'openresa','openstc_pret_uom_hour')[1]
        hour_uom = uom_obj.browse(cr, uid, hour_uom_id, context=context)
        day_uom_id = data_obj.get_object_reference(cr, uid, 'openresa','openstc_pret_uom_day')[1]
        day_uom = uom_obj.browse(cr, uid, day_uom_id, context=context)
        categ_uom_id = data_obj.get_object_reference(cr, uid, 'openresa','openstc_pret_uom_categ_resa')[1]
        #first, retrieve qty according to product_uom
        res = length
        if record.uos_id and record.uos_id.category_id.id == categ_uom_id:
            if record.uom_id.id <> hour_uom_id:
                res = self.pool.get('product.uom')._compute_qty_obj(cr, uid, hour_uom, length,record.uos_id, context=context)
        #else, compute qty for day uom by default
        else:
            res = self.pool.get('product.uom')._compute_qty_obj(cr, uid, hour_uom, length, day_uom, context=context)
        return res

product_product()

class product_category(OpenbaseCore):
    _name = "product.category"
    _inherit = 'product.category'
    _description = "Product Category"
    _columns = {
        'cat_id':fields.many2one('product.category','category', ondelete='cascade'),

    }
    _defaults = {
        'isroomtype': lambda *a: 1,
    }
product_category()

class hotel_reservation(OpenbaseCore):
    _inherit = "hotel.reservation"
    _columns = {
        'manager_id':fields.related('reservation_line','reserve_product','openresa_property_manager_id', type='many2one', relation='res.users', string='Gestionnaire',store=False),
        }
hotel_reservation()

class res_partner(OpenbaseCore):
    _inherit = "res.partner"

    """
    @param prod_ids_and_qties: list of dict containing each prod_id - qty to retrieve their prices
    @param pricelist_id: id of the pricelist to retrieve prices
    @return: list of dict [{'prod_id':id, price:float_price}] according to pricelist_id correctly formated
    (instead of original methods of this nasty OpenERP)
    """
    def get_bookable_prices(self, cr, uid, partner_id, prod_ids_and_qties, checkin, checkout, pricelist_id=False, context=None):
        if not pricelist_id:
            pricelist_id = self.pool.get("res.partner").read(cr, uid, partner_id, ['property_product_pricelist'], context=context)['property_product_pricelist'][0]
        length_resa = self.pool.get('hotel.reservation').get_length_resa(cr, uid, checkin, checkout, context=context)
        length_fnct = self.pool.get('product.product').get_temporal_uom_qty
        pricelist_obj = self.pool.get('product.pricelist')
        values = [(item['prod_id'],length_fnct(cr, uid, item['prod_id'],length_resa, context=context) * item['qty'], partner_id)for item in prod_ids_and_qties]
        #get prices from pricelist_obj
        res = pricelist_obj.price_get_multi(cr, uid, [pricelist_id], values, context=context)
        if 'item_id' in res:
            item_id = res.pop('item_id')
        #format return to be callable by xmlrpc (because dict with integer on keys raises exceptions)
        ret = {}
        for key,val in res.items():
            ret.update({str(key):val[pricelist_id]})
        return ret

res_partner()