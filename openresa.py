# -*- coding: utf-8 -*-

##############################################################################
#
#    OpenCivil module for OpenERP, module Etat-Civil
#    Copyright (C) 200X Company (<http://website>) pyf
#
#    This file is a part of penCivil
#
#    penCivil is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    penCivil is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
from datetime import datetime,timedelta
from osv import fields, osv
import netsvc
from tools.translate import _
from mx.DateTime.mxDateTime import strptime
import time
import types
import base64
import unicodedata
import re
import pytz
import calendar
import logging
import openerp
import os
import tools
from datetime import datetime
from siclic_time_extensions import weeks_between, days_between
import html_builder

#----------------------------------------------------------
# Fournitures
#----------------------------------------------------------
class product_product(osv.osv):


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


# i create model in this file to avoid inter-dependance between hotel.reservation and this one
# actually, they have many2one on each other
#this object is fully implemented in openresa_recurrence.py file
class openresa_reservation_recurrence(osv.osv):
    _name = 'openresa.reservation.recurrence'
    _inherits = {'hotel.reservation':'template_id'}
    _columns = {
            'template_id':fields.many2one('hotel.reservation','Template', required=True, ondelete='cascade')
        }

openresa_reservation_recurrence()

class hotel_reservation_line(osv.osv):
    _name = "hotel_reservation.line"
    _inherit = "hotel_reservation.line"

    _AVAILABLE_ACTION_VALUES = [('nothing','Pas d\'intervention'),('inter','Intervention à générer'),('inter_ok','Intervention générée')]

    def name_get(self, cr, uid, ids, context=None):
        ret = []
        for line in self.browse(cr, uid, ids, context):
            ret.append((line.id,'%s %s' % (line.qte_reserves, line.reserve_product)))
        return ret
    #TODO: check if useless ?
    #Ligne valide si (infos XOR no_infos)
    def _calc_line_is_valid(self, cr, uid, ids, name, args, context=None):
        ret = {}
        for line in self.browse(cr, uid, ids):
            ret.update({line.id: (line.infos and not line.no_infos) or (not line.infos and line.no_infos)})
        return ret
    #TODO: check if useless ?
    def _get_line_to_valide(self, cr, uid, ids, context=None):
        return ids

    def _get_state_line(self, cr, uid, context=None):
        res = self.pool.get("hotel.reservation").fields_get(cr, uid, 'state', context=context)
        return res['state']['selection']

    def _calc_qte_dispo(self, cr, uid, ids, name, args, context=None):
        prod_id_to_line = {}
        if not context:
            context = {}
        resa_ids = []
        ret = {}.fromkeys(ids,{'dispo':False,'qte_dispo':0.0})
        if 'qte_dispo' in name:
            #get all resa linked with lines
            for line in self.browse(cr, uid, ids):
                if line.line_id and not line.line_id.id in resa_ids:
                    resa_ids.append(line.line_id.id)
            #for each resa, compute the qty_available
            for resa in self.pool.get("hotel.reservation").browse(cr, uid, resa_ids):
                prod_ids = [x.reserve_product.id for x in resa.reservation_line]
                #get available prods_qty : {prod_id:qty}
                available = self.pool.get("hotel.reservation").get_prods_available_and_qty( cr, uid, resa.checkin, resa.checkout, prod_ids=prod_ids, where_optionnel='and hr.id <> ' + str(resa.id), context=context)
                #link prod qty available to resa_line associated
                for line in resa.reservation_line:
                    ret.update({line.id:{'qte_dispo':available[str(line.reserve_product.id)]}})
                    if 'dispo' in name:
                        ret[line.id].update({'dispo':available[str(line.reserve_product.id)] >= line.qte_reserves})
        elif 'dispo' in name:
            for line in self.browse(cr, uid, ids):
                ret.update({line.id:{'dispo':line.qte_dispo >= line.qte_reserves}})
        return ret

    def _get_amount(self, cr, uid, ids, name, args, context=None):
        ret = {}.fromkeys(ids, 0.0)
        for line in self.browse(cr, uid, ids, context):
            amount = line.pricelist_amount * line.qte_reserves
            ret.update({line.id:amount})
            #TOCHECK: is there any taxe when collectivity invoice people ?
        return ret

    def _get_complete_name(self, cr, uid, ids, name, args, context=None):
        ret = {}
        weekday_to_str = {0:'Lundi',1:'Mardi',2:'Mercredi',3:'Jeudi',4:'Vendredi',5:'Samedi',6:'Dimanche'}
        for line in self.browse(cr, uid, ids, context=context):
            dt_checkin = fields.datetime.context_timestamp(cr, uid, datetime.strptime(line.checkin,'%Y-%m-%d %H:%M:%S'), context=context)
            dt_checkout = fields.datetime.context_timestamp(cr, uid, datetime.strptime(line.checkout,'%Y-%m-%d %H:%M:%S'), context=context)
            checkin = dt_checkin.strftime('%Y-%m-%d %H:%M:%S')
            checkout = dt_checkout.strftime('%Y-%m-%d %H:%M:%S')
            weekday_start = calendar.weekday(int(checkin[:4]), int(checkin[5:7]), int(checkin[8:10]))
            weekday_end = calendar.weekday(int(checkout[:4]), int(checkout[5:7]), int(checkout[8:10]))
            date_str = ''

            if weekday_start <> weekday_end:
                date_str = '%s %s - %s %s : ' % (weekday_to_str[weekday_start][:3],checkin[11:16],weekday_to_str[weekday_end][:3],checkout[11:16])
            ret[line.id] = '%s %d x %s (%s)' %(date_str,line.qte_reserves, line.reserve_product.name_template, line.partner_id.name)
        return ret

    """
    @param prod_dict: list of dict of prod and qty to retrieve values (represents produdcts needed for reservation) : [{'prod_id':id,'qty':qty_needed}]
    @param checkin-checkout: dates of checkin-checkout to test
    @return: lines for which current checkin-checkout and prod_dict are in conflicts
    @note: to be used in fields.function calculation and for other uses, as openresa.reservation.choices 'dispo' calculation
    """
    def get_global_conflicting_lines(self,cr, uid, prod_dict, checkin, checkout, context=None):
        ret = []
        prod_ids = [item['prod_id'] for item in prod_dict]
        #compute qties of products already in 'remplir' resa
        available = self.pool.get("hotel.reservation").get_prods_available_and_qty(cr, uid, checkin, checkout, prod_ids=prod_ids, states=['cancel','done','confirm','wait_confirm'], context=context)
        #for each prod desired, retrieve those which are conflicting
        conflicting_prods = []
        for item in prod_dict:
            if available[str(item['prod_id'])] < item['qty']:
                conflicting_prods.append(item['prod_id'])
        #and retrieve lines belonging to conflicting_prods and checkin-checkout
        if conflicting_prods:
            ret.extend(self.search(cr, uid, [('reserve_product.id','in',conflicting_prods),'|',
                                             '&',('line_id.checkin','>=',checkin),('line_id.checkin','<=',checkout),
                                             '&',('line_id.checkout','>=',checkin),('line_id.checkout','<=',checkout)],
                                   context=context))
        return ret


    def _get_conflicting_lines(self, cr, uid, ids, name, args, context=None):
        #by default, returns empty list
        ret = {}.fromkeys(ids,[])
        #get only lines in 'remplir' state
        for line in self.browse(cr, uid, ids, context=context):
            if line.line_id and line.line_id.state == 'remplir':
                ret[line.id] = self.get_global_conflicting_lines(cr, uid, [{'prod_id':line.reserve_product.id,'qty':line.qte_reserves}], line.line_id.checkin, line.line_id.checkout, context)
        return ret

    ''' get conflicting lines for each reservation 's line'''
    def _get_conflicting_lines_old(self, cr, uid, ids, name, args, context=None):
        conflicting_lines = {}
        #for each line
        for line in self.browse(cr, uid, ids, context=context):
            conflicting_lines[line.id] = []
            temp_lines = []
            sum_qty = 0
            if line.line_id.id != False and line.reserve_product.id != False and line.checkin!=False and line.checkout!=False:
                #get reservation
                resa_obj = self.pool.get("hotel.reservation").browse(cr, uid, line.line_id.id)
                if rsa_obj.state == "remplir":
                    #get product for line reservation
                    prod_obj = self.pool.get("product.product").browse(cr, uid, line.reserve_product.id)
                    #Get conflicting lines on line 's product
                    results = self.get_lines_by_prod(cr, line.reserve_product.id, line.checkin, line.checkout, where_optionnel='and hr.id <> ' + str(line.line_id.id)).fetchall()
                    if len(results)> 0 :
                        #sum quantity of product request on all conflicting lines
                        for line_id, qty_reserved  in results :
                            sum_qty += qty_reserved
                            temp_lines.append(line_id)
                        #If there is not enough quantiy of product set conflicting lines for this line
                        if (prod_obj.virtual_available - sum_qty) < line.qte_reserves :
                                conflicting_lines[line.id] = temp_lines

        return conflicting_lines

    _columns = {
        'categ_id': fields.many2one('product.category','Type d\'article'),
        "reserve_product": fields.many2one("product.product", "Article réservé", domain=[('openstc_reservable','=',True)]),
        "qte_reserves":fields.float("Qté désirée", digits=(3,2)),
        'pricelist_amount':fields.float('Price from pricelist'),
        'pricelist_item':fields.many2one('product.pricelist.item','Pricelist item of invoicing'),
        'dispo':fields.function(_calc_qte_dispo, string="Disponible", method=True, multi="dispo", type='boolean'),
        "infos":fields.char("Informations supplémentaires",size=256),
        "name":fields.char('Libellé', size=128),
        'state':fields.related('line_id','state', type='selection',string='Etat Résa', selection=_get_state_line, readonly=True),
        'uom_qty':fields.float('Qté de Référence pour Facturation',digit=(2,1)),
        'amount':fields.function(_get_amount, string="Prix (si tarifé)", type="float", method=True, store=False),
        'qte_dispo':fields.function(_calc_qte_dispo, method=True, string='Qté Dispo', multi="dispo", type='float'),
        'action':fields.selection(_AVAILABLE_ACTION_VALUES, 'Action'),
        'state':fields.related('line_id','state', type='char'),
        'partner_id':fields.related('line_id','partner_id', type="many2one", relation="res.partner"),
        'checkin':fields.related('line_id','checkin', type="datetime"),
        'checkout':fields.related('line_id','checkout', type="datetime"),
        'resa_name':fields.related('line_id','name',type="char"),
        'complete_name':fields.function(_get_complete_name, type="char", string='Complete Name', size=128)
        }

    _defaults = {
     'qte_reserves':lambda *a: 1,
     'state':'remplir',
     'action':'nothing',
        }

    #TODO: check if useless ?
    def plan_inter(self, cr, uid, ids, context=None):
        self.write(cr, uid, ids, {'action':'inter'})
        return {'type':'ir.actions.act_window.close'}
    #@TOCHECK: useless ?
    def unplan_inter(self, cr, uid, ids, context=None):
        self.write(cr, uid, ids, {'action':'nothing'})
        return {'type':'ir.actions.act_window.close'}

    '''' Get conflicting lines by product '''
    def get_lines_by_prod(self, cr, prod, checkin, checkout, states=['remplir'], where_optionnel=""):
        cr.execute("select hrl.id, hrl.qte_reserves \
                    from hotel_reservation_line as hrl \
                    join hotel_reservation as hr  on hr.id = hrl.line_id \
                    where reserve_product = %s \
                    and hr.state  in%s \
                    and (hr.checkin, hr.checkout) overlaps ( timestamp %s, timestamp %s ) \
                    " + where_optionnel , (prod, tuple(states), checkin, checkout))
        return cr

    #TODO : check lines (for non manager user only) : if product has max_qty, lines must not reserve more than max_qty of this product
    def _check_max_qties(self, cr, uid, ids, context=None):
        is_manager = self.pool.get("res.users").search(cr, uid, [('id','=',uid),('groups_id.code','=','HOTEL_MANA')])
        if not is_manager:
            for line in self.browse(cr, uid, ids, context=context):
                #if one line does not match criteria, return False and raise exception
                if line.reserve_product.max_bookable_qty and line.qte_reserves > line.reserve_product.max_bookable_qty:
                    return False
        return True

    _constraints = [(_check_max_qties, _('You can not reserve more than qty max for your product'), ['reserve_product','qte_reserves'])]

hotel_reservation_line()

class hotel_reservation(osv.osv):
    AVAILABLE_IN_OPTION_LIST = [('no','Rien à Signaler'),('in_option','Réservation En Option'),('block','Réservation bloquée')]
    _name = "hotel.reservation"
    _order = "state_num, create_date desc"
    _inherit = "hotel.reservation"
    _description = "Réservations"

    """
    @param record: browse_record of hotel.reservation for which to generate hotel.folio report
    @return: id or attachment created for this record
    @note: hotel.folio report is created on hotel.reservation because hotel.folio has not any form view for now
    """

    def _create_report_folio_attach(self, cr, uid, record, context=None):
        #sources insipered by _edi_generate_report_attachment of EDIMIXIN module
        ir_actions_report = self.pool.get('ir.actions.report.xml')
        report_id = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'openresa','folio_report')[1]
        ret = False
        if report_id:
            report = ir_actions_report.browse(cr, uid, report_id,context=context)
            report_service = 'report.' + report.report_name
            service = netsvc.LocalService(report_service)
            (result, format) = service.create(cr, uid, [folio.id for folio in record.folio_id], {'model': self._name}, context=context)
            eval_context = {'time': time, 'object': record}
            if not report.attachment or not eval(report.attachment, eval_context):
                # no auto-saving of report as attachment, need to do it manually
                result = base64.b64encode(result)
                file_name = 'Facturation_' + record.reservation_no
                file_name = re.sub(r'[^a-zA-Z0-9_-]', '_', file_name)
                file_name += ".pdf"
                ir_attachment = self.pool.get('ir.attachment').create(cr, uid,
                                                                      {'name': file_name,
                                                                       'datas': result,
                                                                       'datas_fname': file_name,
                                                                       'res_model': self._name,
                                                                       'res_id': record.id},
                                                                      context=context)
                ret = ir_attachment
                record.write({'invoice_attachment_id': ret})
        return ret


    def remove_accents(self, str):
        return ''.join(x for x in unicodedata.normalize('NFKD',str) if unicodedata.category(x)[0] == 'L')

    def _custom_sequence(self, cr, uid, context):
        seq = self.pool.get("ir.sequence").next_by_code(cr, uid, 'resa.number',context)
        return seq

    #TODO: check if useless ?
    def _calc_in_option(self, cr, uid, ids, name, args, context=None):
        ret = {}
        #fixes : calc only for resa, avoiding inheritance bugs
        for resa in self.pool.get("hotel.reservation").browse(cr, uid, ids, context):
            ret[resa.id] = 'no'
            date_crea = strptime(resa.date_order, '%Y-%m-%d %H:%M:%S')
            checkin = strptime(resa.checkin, '%Y-%m-%d %H:%M:%S')
            for line in resa.reservation_line:
                #Vérif si résa dans les délais, sinon, in_option est cochée
                d = timedelta(days=int(line.reserve_product.sale_delay and line.reserve_product.sale_delay or 0))
                #Si l'un des produits est hors délai
                if date_crea + d > checkin:
                    if line.reserve_product.bloquant:
                        ret[resa.id] = 'block'
                    elif ret[resa.id] == 'no':
                        ret[resa.id] = 'in_option'
        return ret

    def get_resa_modified(self, cr, uid, ids, context=None):
        return ids

    def return_state_values(self, cr, uid, context=None):
        return [('draft', 'Saisie des infos personnelles'),('confirm','Réservation confirmée'),('cancel','Annulée'),('in_use','Réservation planifiée'),('done','Réservation Terminée'), ('remplir','Saisie de la réservation'),('wait_confirm','En Attente de Confirmation')]

    def _get_state_values(self, cr, uid, context=None):
        return self.return_state_values(cr, uid, context)

    def _get_state_num(self, cr, uid, ids,  name, args, context=None):
        res={}
        for obj in self.browse(cr, uid, ids, context):
            res[obj.id] = (obj.state=='remplir' and 1) or (obj.state=='draft' and 2) or (obj.state=='confirm' and 3) or (obj.state=='done' and 4) or 5
        return res

    def _get_amount_total(self, cr, uid, ids, name, args, context=None):
        ret = {}
        for resa in self.browse(cr, uid, ids, context=None):
            amount_total = 0.0
            all_dispo = True
            for line in resa.reservation_line:
                if all_dispo and not line.dispo:
                    all_dispo = False
                amount_total += line.amount
            ret[resa.id] = {'amount_total':amount_total,'all_dispo':all_dispo}
        return ret

    """
    action rights for manager only
    - only manager can do it, because imply stock evolutions and perharps treatment of some conflicts
    """
    def managerOnly(self, cr, uid, record, groups_code):
        return 'HOTEL_MANA' in groups_code

    """
    action rights for manager or owner of a record
    - claimer can do these actions on its own records,
    - officer can make these actions for claimer which does not have account,
    - else, manager can also do it
    """
    def ownerOrOfficer(self, cr, uid, record, groups_code):
        #if not rights, compute rights for offi/manager
        ret = 'HOTEL_OFFI' in groups_code or 'HOTEL_MANA' in groups_code
        if not ret:
            #compute rights for owner
            for contact in record.partner_id.address:
                if uid == contact.user_id.id:
                    ret = True
                    break
            ret = ret and 'HOTEL_USER' in groups_code
        return ret

    _actions = {
        'confirm': lambda self,cr,uid,record, groups_code: self.managerOnly(cr, uid, record, groups_code)  and record.state == 'remplir',
        'cancel': lambda self,cr,uid,record, groups_code: self.managerOnly(cr, uid, record, groups_code)  and record.state == 'remplir',
        'done': lambda self,cr,uid,record, groups_code: self.managerOnly(cr, uid, record, groups_code) and record.state == 'confirm',
    }

    def _get_fields_resources(self, cr, uid, ids, name, args, context=None):
        res = {}

        for obj in self.browse(cr, uid, ids, context=context):
            res[obj.id] = {}
            field_ids = obj.reservation_line
            val = []
            for item in field_ids:
                if obj.state in ('remplir','cancel'):
                    tooltip = " souhaitée: " + str(int(item.qte_reserves))
                    if item.dispo and obj.state!='cancel' :
                        tooltip += " ,disponible: " + str(int(item.qte_dispo))
                else :
                    tooltip = " réservée : " + str(int(item.qte_reserves))
                val.append({'id': item.reserve_product.id,  'name' : item.reserve_product.name_get()[0][1], 'type': item.reserve_product.type_prod,  'quantity' : item.qte_reserves, 'tooltip' : tooltip})
            res[obj.id].update({'resources':val})
        return res

    def _get_actions(self, cr, uid, ids, myFields ,arg, context=None):
        #default value: empty string for each id
        ret = {}.fromkeys(ids,'')
        groups_code = []
        groups_code = [group.code for group in self.pool.get("res.users").browse(cr, uid, uid, context=context).groups_id if group.code]

        #evaluation of each _actions item, if test returns True, adds key to actions possible for this record
        for record in self.browse(cr, uid, ids, context=context):
            #ret.update({inter['id']:','.join([key for key,func in self._actions.items() if func(self,cr,uid,inter)])})
            ret.update({record.id:[key for key,func in self._actions.items() if func(self,cr,uid,record,groups_code)]})
        return ret

    def get_data_from_xml(self, cr, uid, module, model, context=None):
        ret = self.pool.get('ir.model.data').get_object_reference(cr, uid, module, model)
        ret = ret[1] if ret else False
        return ret

    def generate_html_plannings_for(self, cr, uid, bookable_ids, start_date, end_date):
        for planning in self.generate_plannings_for(cr, uid, bookable_ids, start_date, end_date):
            html_planning = self.format_plannings_with(planning, 'html')
        return html_planning

    def generate_plannings_for(self, cr, uid, bookable_ids, start_date, end_date):
        """
        This function generate weekly html plannings of the given resources.

        :param bookable_ids: The bookable resources ids included in plannings
        :param start_date: The start date of the planning
        :param end_date: Then end date of the planning
        :return: List[Dict['bookable_name':String, weeks: List[hotel_reservation]]]
        """
        weeks = weeks_between(datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S"),
                              datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S"))
        plannings = list()
        bookables = self.pool.get('product.product').read(cr, uid, bookable_ids, ['name'])
        for bookable in bookables:
            plannings.append(
                {'bookable_name': bookable['name'], 'weeks': self.event_list_for_weeks(cr, uid, bookable['id'], weeks)})
        return plannings

    def event_list_for_weeks(self, cr, uid, bookable_id, weeks):
        """
        Retrieve events for a given bookable, and given weeks

        :param bookable_id: Integer the bookable id
        :param weeks: a list of tuple [(datetime,datetime)]
        :return: List[List[hotel_reservation]]
        """
        bookable_events = list()
        for week in weeks:
            bookable_events.append(self.event_list_for_week(cr, uid, bookable_id, week))
        return bookable_events

    def event_list_for_week(self, cr, uid, bookable_id, week):
        """
        Retrieve events ids for a given bookable, and given week

        :param bookable_id: Integer the bookable id
        :param week: Tuple[Datetime, Datetime]
        :return: Dict['first_day':String,'last_day': String, 'bookings': Dict[datetime: List[hotel_reservation]]]
        """
        first_day = datetime.strftime(week[0], '%Y-%m-%d %H:%M:%S')
        last_day = datetime.strftime(week[1], '%Y-%m-%d %H:%M:%S')

        week_events_ids = self.search(cr, uid,
                                      [('reservation_line.reserve_product.id', '=', bookable_id),
                                       ('state', '=', 'confirm'),
                                       '|',
                                       '&', ('checkin', '>=', first_day), ('checkin', '<=', last_day),
                                       '&', ('checkout', '>=', first_day), ('checkout', '<=', last_day)])
        week_events = {'first_day': first_day, 'last_day': last_day,
                       'bookings': self.build_events_data_dictionary(cr, uid, week_events_ids)}

        week_days = days_between(week[0], week[1])
        events_by_day = list()
        for day in week_days:
            events_by_day.append((day, filter(lambda event: (event.get('start_hour').date() <= day.date()) &
                                                            (event.get('end_hour').date() >= day.date()),
                                              week_events.get('bookings'))))
        week_events['bookings'] = events_by_day
        return week_events

    def build_events_data_dictionary(self, cr, uid, event_ids):
        """
        Format data to expose weekly planning through API

        :param event_ids: List[Integer]
        :return: List[Dict]
        """
        events = self.read(cr, uid, event_ids,
                           ['name', 'checkin', 'checkout', 'partner_id', 'partner_order_id', 'resources',
                            'confirm_note'])

        events_dictionaries = map(lambda event:
                                  {
                                      'name': event.get('name'),
                                      'start_hour': datetime.strptime(event.get('checkin'), "%Y-%m-%d %H:%M:%S"),
                                      'end_hour':  datetime.strptime(event.get('checkout'), "%Y-%m-%d %H:%M:%S"),
                                      'booker_name': event.get('partner_id')[1],
                                      'contact_name': event.get('partner_order_id')[1],
                                      'resources': map(lambda r: {'name': r.get('name'), 'quantity': r.get('quantity')},
                                                       event.get('resources')),
                                      'note': event.get('confirm_note')
                                  },
                                  events)
        return events_dictionaries

    def format_plannings_with(self, plannings, req_format):
        if req_format == 'html':
            return html_builder.format_resource_plannings(plannings)


    _columns = {
        'create_uid': fields.many2one('res.users', 'Created by', readonly=True),
        'write_uid': fields.many2one('res.users', 'Writed by', readonly=True),
        'deleted_at': fields.date('Deleted date'),
        'confirm_at': fields.date('Confirm date'),
        'done_at': fields.date('Done date'),
        'cancel_at': fields.date('Cancel date'),
        'state': fields.selection(_get_state_values, 'Etat', readonly=True),
        'state_num': fields.function(_get_state_num, string='Current state', type='integer', method=True,
                                     store={'hotel.reservation': (get_resa_modified, ['state'], 20)}),
        'create_date': fields.datetime('Create Date', readonly=True),
        'write_date': fields.datetime('Write Date', readonly=True),
        'in_option': fields.function(_calc_in_option, string="En Option", selection=AVAILABLE_IN_OPTION_LIST,
                                     type="selection", method=True, store={
            'hotel.reservation': (get_resa_modified, ['checkin', 'reservation_line'], 10)},
                                     help=("Une réservation mise en option signifie que votre demande est prise en compte mais \
                                            dont on ne peut pas garantir la livraison à la date prévue.\
                                            Une réservation bloquée signifie que la réservation n'est pas prise en compte car nous ne pouvons pas \
                                            garantir la livraison aux dates indiquées")),
        'name': fields.char('Nom Manifestation', size=128, required=True),
        'resources': fields.function(_get_fields_resources, multi='field_resources', method=True,
                                        type='char', store=False),

        'site_id': fields.many2one('openstc.site', 'Site (Lieu)'),
        'prod_id': fields.many2one('product.product', 'Ressource'),
        'openstc_partner_id': fields.many2one('res.partner', 'Demandeur', help="Personne demandant la réservation."),
        'resa_checkout_id': fields.many2one('openstc.pret.checkout', 'Etat des Lieux associé'),
        'amount_total': fields.function(_get_amount_total, type='float', string='Amount Total', method=True,
                                        multi="resa",
                                        help='Optionnal, if positive, a sale order will be created once resa validated and invoice will be created once resa done.'),
        'all_dispo': fields.function(_get_amount_total, type="boolean", string="All Dispo", method=True, multi="resa"),
        'date_choices': fields.one2many('openresa.reservation.choice', 'reservation_id', 'Choices of dates'),
        'recurrence_id': fields.many2one('openresa.reservation.recurrence', 'From recurrence'),
        'is_template': fields.boolean('Is Template', help='means that this reservation is a template for a recurrence'),
        'actions': fields.function(_get_actions, method=True, string="Actions possibles", type="char", store=False),
        'partner_type': fields.related('partner_id', 'type_id', type='many2one', relation='openstc.partner.type',
                                       string='Type du demandeur', help='...'),

        'contact_phone': fields.related('partner_invoice_id', 'phone', type='char', string='Phone contact', help='...'),
        'partner_mail': fields.char('Email Demandeur', size=128, required=False),


        'people_name': fields.char('Name', size=128),
        'people_phone': fields.char('Phone', size=16),
        #'people_email': fields.char('Email', size=128),
        'people_street':fields.char('Street',size=128),
        'people_city':fields.char('City',size=64),
        'people_zip':fields.char('Zip',size=5),
        'is_citizen': fields.boolean('Claimer is a citizen'),

        'note': fields.text('Note de validation'),
        'confirm_note': fields.text('Note de validation'),
        'cancel_note': fields.text('Note de refus'),
        'done_note': fields.text('Note de clôture'),
        'send_invoicing': fields.boolean('Send invoicing by email'),
        'invoice_attachment_id': fields.integer('Attachment ID'),
        'whole_day':fields.boolean('Whole day'),
    }
    _defaults = {
                 'in_option': lambda *a :0,
                 'state': lambda *a: 'remplir',
                 'reservation_no': lambda self,cr,uid,ctx=None:self._custom_sequence(cr, uid, ctx),
        }

    def search(self, cr, uid, args, offset=0, limit=None, order=None, context=None, count=False):
        if order in (' ',''): order=None
        #Keep simple resa and only template for reccurence
        deleted_domain = []
        for s in args :
            if 'deleted_at' in s:
                args.remove(s)
                deleted_domain = [('deleted_at','=', False)]
        args.extend(deleted_domain)
        return super(hotel_reservation, self).search(cr, uid, args, offset, limit, order, context, count)



    def _check_dates(self, cr, uid, ids, context=None):
        for resa in self.browse(cr, uid, ids, context):
            if resa.checkin >= resa.checkout:
                return False
        return True

    _constraints = [(_check_dates, _("Your checkin is greater than your checkout, please modify them"), ['checkin','checkout'])]

    def format_vals(self, cr, uid, checkin, checkout, context=None):
        def force_seconds_date(vals):
            if vals and len(vals) > 16:
                vals = vals[:16] + ':00'
        return vals
        checkin = force_seconds_date(checkin)
        checkout = force_seconds_date(checkout)
        return True

    def resolve_default_partner_values(self, cr, uid, vals):
        """
        @note: Return default values for partner, partner_adresses and pricelist
        @param vals: dict of data to store in db (from write or create methods)
        @return: new dict 'vals' overriden with default values (if needed)
        """
        partner_id = vals.get('partner_id', False)
        #raise an exception if data are not correct
        if not partner_id and not vals.get('is_citizen',False):
            raise osv.except_osv('Inconsistent Data', 'The booking is missing a partner')
        #for citizen claimers, retrieve default partner created in xml
        elif not partner_id:
            partner_id = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'openresa','openresa_partner_part')[1]
            if not partner_id:
                raise osv.except_osv('Inconsistent Data', 'The default value for citizen Claimer is missing, please restart your server')
            else:
                vals.update({'partner_id':partner_id})
        #then, if contact is missing, retrieve first address linked with partner    
        partner = self.pool.get('res.partner').read(cr, uid, partner_id, ['address', 'property_product_pricelist'])
        addresses = partner['address']
        if not vals.get('partner_order_id', False) and addresses:
            vals.update({'partner_order_id':addresses[0],
                         'partner_shipping_id':addresses[0],
                         'partner_invoice_id':addresses[0]})
        elif not addresses:
            raise osv.except_osv('Inconsistent Data', 'The default value for citizen Claimer-Contact is missing, please restart your server')
        vals.update({'pricelist_id':partner.get('property_product_pricelist',[False,'none'])[0]})
        return vals

    def create(self, cr, uid, values, context=None):
        if not 'state' in values or values['state'] == 'remplir':
            values['shop_id'] = self.pool.get("sale.shop").search(cr, uid, [], limit=1)[0]
        if 'checkin' in values:
            if len(values['checkin']) > 10:
                values['checkin'] = values['checkin'][:-3] + ':00'
        if 'checkout' in values:
            if len(values['checkout']) >10:
                values['checkout'] = values['checkout'][:-3] + ':00'
        values = self.resolve_default_partner_values(cr, uid, values)

        return super(hotel_reservation, self).create(cr, uid, values, context)

    def validate(self, cr, uid, ids, vals, context=None):
        if not isinstance(ids, list):
            ids = [ids]
        wkf_service = netsvc.LocalService('workflow')
        resa_count = 0
        for resa in self.browse(cr, uid, ids, context=context):
            #count to know how many resa have been requested to be confirmed,
            #recurrence is updated to confirmed only if one or more recurrence has been requested to be confirmed
            wkf_service.trg_validate(uid, 'hotel.reservation', resa.id, vals['state'], cr)
            if resa.recurrence_id and resa_count > 0 :
                resa.recurrence_id.write({'recurrence_state':'in_use'})
        return True

    def write(self, cr, uid, ids, vals, context=None):
        isList = isinstance(ids, types.ListType)
        if isList == False :
            ids = [ids]
        if context == None:
            context = {}
        if 'checkin' in vals:
            if len(vals['checkin']) > 10:
                vals['checkin'] = vals['checkin'][:-3] + ':00'
        if 'checkout' in vals:
            if len(vals['checkout']) >10:
                vals['checkout'] = vals['checkout'][:-3] + ':00'
        state = None
        if vals.has_key('state_event') :
            state = vals.get('state_event')
            vals[state+'_at'] = datetime.now().strftime('%Y-%m-%d')
            vals.pop('state_event')
        res = super(hotel_reservation, self).write(cr, uid, ids, vals, context)
        if state!= None :
            vals.update( { 'state' : state } )
            self.validate(cr, uid, ids, vals, context)

        return res

    def unlink(self, cr, uid, ids, context=None):
        if not isinstance(ids, list):
            ids = [ids]
        line_ids = []
        for resa in self.browse(cr, uid, ids, context):
            line_ids.extend([x.id for x in resa.reservation_line])
        self.pool.get("hotel_reservation.line").unlink(cr, uid, line_ids, context)
        return super(hotel_reservation, self).unlink(cr, uid, ids, context)

    def onchange_openstc_partner_id(self, cr, uid, ids, openstc_partner_id=False):
        return {'value':{'partner_id':openstc_partner_id}}

    def onchange_partner_shipping_id(self, cr, uid, ids, partner_shipping_id=False):
        email = False
        if partner_shipping_id:
            email = self.pool.get("res.partner.address").browse(cr, uid, partner_shipping_id).email
        return {'value':{'partner_mail':email,'partner_invoice_id':partner_shipping_id,'partner_order_id':partner_shipping_id}}

    def confirmed_reservation(self,cr,uid,ids):
        for resa in self.browse(cr, uid, ids):
            if self.is_all_dispo(cr, uid, ids[0]):
                if resa.in_option == 'block':
                    raise osv.except_osv(_("Error"),_("""Your resa is blocked because your expected date is too early so that we can not supply your products at time"""))

                attach_sale_id = []
                line_ids = []
                if not resa.recurrence_id or resa.is_template:
                    folio_id = self.create_folio(cr, uid, [resa.id])

                    attachment_id = self._create_report_folio_attach(cr, uid, resa)
                    wf_service = netsvc.LocalService('workflow')
                    wf_service.trg_validate(uid, 'hotel.folio', folio_id, 'order_confirm', cr)
                    folio = self.pool.get("hotel.folio").browse(cr, uid, folio_id)
                    #move_ids store moves created by folio and reverse moves created to reset stock moves
                    move_ids = []
                    for picking in folio.order_id.picking_ids:
                        for move in picking.move_lines:
                            move_ids.append(move.id)
                            #On crée les mvts stocks inverses pour éviter que les stocks soient impactés
                            new_move_id = self.pool.get("stock.move").copy(cr, uid, move.id, {'picking_id':move.picking_id.id,'location_id':move.location_dest_id.id,'location_dest_id':move.location_id.id,'state':'draft'})
                            move_ids.append(new_move_id)

                    self.pool.get("stock.move").action_done(cr, uid, move_ids)
                    #Send invoicing only if user wants to
                    if resa.send_invoicing:
                        attach_sale_id.append(attachment_id)
                #send mail with optional attaches on products and the sale order pdf attached
                self.envoyer_mail(cr, uid, ids, {'state':'validated'}, attach_ids=attach_sale_id)
                self.write(cr, uid, ids, {'state':'confirm'})
                return True
            else:
                raise osv.except_osv(_("""Not available"""),_("""Not all of your products are available on those quantities for this period"""))
                return False
        return True

    def waiting_confirm(self, cr, uid, ids):
        if self.is_all_dispo(cr, uid, ids[0]):
            self.envoyer_mail(cr, uid, ids, {'state':'waiting'})
            self.write(cr, uid, ids, {'state':'wait_confirm'})
            return True
        raise osv.except_osv(_("""Not available"""),_("""Not all of your products are available on those quantities for this period"""))
        return False

    def cancelled_reservation(self, cr, uid, ids):
        self.envoyer_mail(cr, uid, ids, {'state':'error'})
        self.write(cr, uid, ids, {'state':'cancel'})
        return True


    def redrafted_reservation(self, cr, uid, ids):
        self.write(cr, uid, ids, {'state':'remplir'})
        return True

    def done_reservation(self, cr, uid, ids):
        if isinstance(ids, list):
            ids = ids[0]
        resa = self.browse(cr, uid, ids)
        wf_service = netsvc.LocalService("workflow")
        inv_ids = []
        attach_ids = []
        #Create invoice from each folio
        for folio in resa.folio_id:
            wf_service.trg_validate(uid, 'hotel.folio', folio.id, 'manual_invoice', cr)
        resa.refresh()
        #Validate invoice(s) created
        for folio in resa.folio_id:
            for inv in folio.order_id.invoice_ids:
                print(inv.state)
                wf_service.trg_validate(uid, 'account.invoice', inv.id, 'invoice_open', cr)
                inv_ids.append(inv.id)
        #send mail to notify user if opt_out not checked and if there is invoice(s)
        attach_id = self._create_report_folio_attach(cr, uid, resa)
        if inv_ids and resa.send_invoicing:
            attaches = [attach_id]
            self.envoyer_mail(cr, uid, [ids], vals={'state':'done'}, attach_ids=attaches)
        self.write(cr, uid, ids, {'state':'done'})
        return True

    #TODO: change openstc_manager for hotel.group_manager group
    def need_confirm(self, cr, uid, ids):
        reservations = self.browse(cr, uid, ids)
        etape_validation = False
        group_manager_id = self.pool.get("ir.model.data").get_object_reference(cr, uid, 'hotel','group_hotel_manager')
        #@TODO: if not found, perharps groups has been deleted, have to make an assert
        #@TODO: check group_manager_id with user['groups_id'] instead of using a loop (optimize)
        if group_manager_id:
            for group in self.pool.get('res.users').browse(cr, uid, uid).groups_id:
                if group.id == group_manager_id[1]:
                    return False

        #else, check each seuil confirm products
        for resa in reservations:
                for line in resa.reservation_line:
                    #Si l'un des produits dépasse le seuil max autorisé, on force la validation
                    if line.qte_reserves > line.reserve_product.seuil_confirm:
                        etape_validation = True
        return etape_validation
        #return True
    #TODO: check if useless ?
    def not_need_confirm(self, cr, uid, ids):
        return not self.need_confirm(cr, uid, ids)

    def ARemplir_reservation(self, cr, uid, ids):
        for resa in self.browse(cr, uid, ids):
            if resa.is_template or not resa.recurrence_id:
                self.envoyer_mail(cr, uid, ids, {'state':'waiting'})
        self.write(cr, uid, ids, {'state':'remplir'})
        return True

    #Fonction (liée à une action) permettant de pré-remplir la fiche de réservation en fonction des infos du ou des articles sélectionnés
    def default_get(self, cr, uid, fields, context=None):
        res = super(hotel_reservation, self).default_get(cr, uid, fields, context=context)
        #Si pour l'initialisation de la vue, on est passé par l'action "Réserver article(s)" associée aux catalogues produits
        if ('from_product' in context) and (context['from_product']=='1') :
            data = context and context.get('product_ids', []) or []
            produit_obj = self.pool.get('product.product')
            #Pour chaque produit sélectionnés dans la vue tree des catalogues, on crée une ligne de réservation (objet hotel.reservation.line)
            reservation_lines = []
            for produit in produit_obj.browse(cr, uid, data, []):
                reservation_lines.append(self.pool.get('hotel_reservation.line').create(cr, uid, {
                                                                                        'reserve_product':  produit.id,
                                                                                        'categ_id':produit.categ_id.id,
                                                                                        'reserve':[(4, produit.id)],
                                                                                        'pricelist_amount':produit.product_tmpl_id.list_price,
                                                                                        'qte_reserves':1.0
                                                                                }))

            res.update({'reservation_line':reservation_lines})
        #Valeurs par défauts des champs cachés
        return res

    def get_nb_prod_reserved(self, cr, prod_list, checkin, checkout, states=['cancel','done','remplir'], where_optionnel=""):
        cr.execute("select reserve_product, sum(qte_reserves) as qte_reservee \
                    from hotel_reservation as hr, \
                    hotel_reservation_line as hrl \
                    where hr.id = hrl.line_id \
                    and reserve_product in %s \
                    and hr.state not in%s \
                    and (hr.checkin, hr.checkout) overlaps ( timestamp %s, timestamp %s ) \
                    " + where_optionnel + " \
                    group by reserve_product; ", (tuple(prod_list), tuple(states), checkin, checkout))
        return cr

    #main method to control availability of products : returns availability of each prod : {prod_id:qty} matching dates
    def get_prods_available_and_qty(self, cr, uid, checkin, checkout, prod_ids=[], where_optionnel='', states=['cancel','done','remplir'], context=None):
        #if no prod_ids put, we check all prods
        if not prod_ids:
            prod_ids = self.pool.get("product.product").search(cr, uid, [])
        prods = self.pool.get("product.product").browse(cr, uid, prod_ids)
        prod_dispo = {}
        #by default, all qty in stock are available
        for prod in prods:
            prod_dispo.setdefault(str(prod.id), prod.virtual_available)
        #and, if some resa are made to this prods, we substract default qty with all qty reserved at these dates
        results = self.get_nb_prod_reserved(cr, prod_ids, checkin, checkout, where_optionnel=where_optionnel,states=states).fetchall()
        for prod_id, qty_reserved in results:
            prod_dispo[str(prod_id)] -= qty_reserved
        return prod_dispo

    #computed flag to know if booking can be validated or not
    def is_all_dispo(self, cr, uid, id, context=None):
        for line in self.browse(cr, uid, id, context).reservation_line:
            if line.reserve_product.block_booking and not line.dispo:
                return False
        return True

    def is_all_valid(self, cr, uid, id, context=None):
        for line in self.browse(cr, uid, id, context).reservation_line:
            if not line.valide and line.reserve_product.need_infos_supp:
                return False
        return True

    """polymorphism of _create_folio
    @note: manage both individual resa and recurrente resa (1 line = 1 occurrence)
    """
    def create_folio(self, cr, uid, ids, context=None):
        for reservation in self.browse(cr,uid,ids):
            #first, if it is a recurrence, get all occurrences to generate folio, else, keep only current resa
            lines = []
            #checkin and checkout are used to set the highest scale of dates of a recurrence
            checkin = False
            checkout = False
            if reservation.recurrence_id:
                for resa in reservation.recurrence_id.reservation_ids:
                    lines.extend([line for line in resa.reservation_line if resa.all_dispo])
                    #retrieve min and max date for all the recurrence
                    checkin = resa.checkin if not checkin else min(resa.checkin, checkin)
                    checkout = resa.checkout if not checkout else max(resa.checkout, checkout)
            else:
                lines.extend(line for line in reservation.reservation_line)
                checkin = reservation.checkin
                checkout = reservation.checkout
            room_lines = []
            for line in lines:
                room_lines.append((0,0,{
                   'checkin_date':line.line_id.checkin,
                   'checkout_date':line.line_id.checkout,
                   'product_id':line.reserve_product.id,
                   'name':line.reserve_product.name,
                   'product_uom':line.reserve_product.uom_id.id,
                   'product_uom_qty':line.qte_reserves,
                   'product_uos':line.reserve_product.uos_id and line.reserve_product.uos_id.id or line.reserve_product.uom_id.id,
                   'product_uos_qty':line.uom_qty,
                   'price_unit':line.pricelist_amount,
                   }))
            #if resa is from on recurrence, copy all room_lines for each resa (update checkin and checkout for each one)

            folio=self.pool.get('hotel.folio').create(cr,uid,{
                  'date_order':reservation.date_order,
                  'shop_id':reservation.shop_id.id,
                  'partner_id':reservation.partner_id.id,
                  'pricelist_id':reservation.pricelist_id.id,
                  'partner_invoice_id':reservation.partner_invoice_id.id,
                  'partner_order_id':reservation.partner_order_id.id,
                  'partner_shipping_id':reservation.partner_shipping_id.id,
                  'checkin_date': checkin,
                  'checkout_date': checkout,
                  'room_lines':room_lines,
           })
            #TODO: check useless ?
            cr.execute('insert into hotel_folio_reservation_rel (order_id,invoice_id) values (%s,%s)', (reservation.id, folio))

        return folio

    def get_length_resa(self, cr, uid, checkin, checkout, context=None):
        checkin = strptime(checkin, '%Y-%m-%d %H:%M:%S')
        checkout = strptime(checkout, '%Y-%m-%d %H:%M:%S')
        length = (checkout - checkin).hours
        return length


    #@param record: browse_record hotel.reservation.line
    def get_prod_price(self, cr, uid, product_id, uom_qty, partner_id, pricelist_id=False, context=None):
        pricelist_obj = self.pool.get("product.pricelist")
        if not pricelist_id:
            pricelist_id = self.pool.get('res.partner').browse(cr, uid, partner_id, context=context).property_product_pricelist.id
        res = pricelist_obj.price_get_multi(cr, uid, [pricelist_id], [(product_id,uom_qty,partner_id)], context=None)
        return res and (res[product_id][pricelist_id]) or False

    """
    OpenERP internal invoicing compute
    """
    def compute_lines_price(self, cr, uid, ids, context=None):
        values = []
        #get lentgh resa in hours
        for resa in self.browse(cr, uid, ids, context):
            partner_id = resa.partner_id.id
            pricelist_id = resa.pricelist_id and resa.pricelist_id.id or resa.partner.property_product_pricelist.id
            length_resa = self.get_length_resa(cr, uid, resa.checkin, resa.checkout, context=None)
            prod_obj = self.pool.get('product.product')
            for line in resa.reservation_line:
                uom_qty = prod_obj.get_temporal_uom_qty(cr, uid, line.reserve_product.id, length_resa, context)
                unit_price = self.get_prod_price(cr, uid, line.reserve_product.id,
                                          uom_qty,
                                          partner_id,
                                          pricelist_id,
                                          context=context)
                values.append((1,line.id,{'uom_qty':uom_qty,'pricelist_amount':unit_price}))
            self.write(cr, uid, [resa.id], {'reservation_line':values}, context=context)
        return True

    def open_checkout(self, cr, uid, ids, context=None):
        if isinstance(ids, list):
            ids = ids[0]
        ret = {
            'type':'ir.actions.act_window',
            'res_model':'openstc.pret.checkout',
            'view_type':'form',
            'view_mode':'form',
            'target':'new',
            }
        if not context:
            context = {}
        context.update({'reservation_id':ids})
        #if a checkout already exists, we open to the existing id
        resa = self.browse(cr, uid, ids, context)
        if resa.resa_checkout_id:
            ret.update({'res_id':resa.resa_checkout_id.id})
        else:
            #else, we create a new checkout and display it in a new window(we force the creation to be sure that the checkout is saved in db)
            #we get default_values defined in default_get
            values = self.pool.get("openstc.pret.checkout").default_get(cr, uid, [], context=context)
            res_id = self.pool.get("openstc.pret.checkout").create(cr, uid, values)
            ret.update({'res_id':res_id})
        #and display it
        return ret



    """
    @param vals: Dict containing "to" (deprecated) and "state" in ("error","waiting", "validated","done") (required)
    "state" is a shortcut to retrieve template_xml_id
    @param attach_ids: optionnal parameter to manually add attaches to mail
    @note: send mail according to 'state' value
    """
    def envoyer_mail(self, cr, uid, ids, vals=None, attach_ids=[], context=None):
        #TODO: check if company wants to send email (info not(opt_out) in partner)
        #We keep only resa where partner have not opt_out checked
        resa_ids_notif = []
        resa_ids_notif = [resa.id for resa in self.browse(cr, uid, ids)
                          if not resa.partner_id.opt_out
                          and (not resa.recurrence_id or resa.is_template)]
        if resa_ids_notif:
            email_obj = self.pool.get("email.template")
            email_tmpl_id = 0
            prod_attaches = {}
            #first, retrieve template_id according to 'state' parameter
            if 'state' in vals.keys():
                if vals['state'] == "error":
                    email_tmpl_id = email_obj.search(cr, uid, [('model','=',self._name),('name','ilike','annulée')])
                elif vals['state'] == 'waiting':
                    email_tmpl_id = email_obj.search(cr, uid, [('model','=',self._name),('name','ilike','Réserv%Attente')])
                elif vals['state'] == 'done':
                    email_tmpl_id = email_obj.search(cr, uid, [('model','=',self._name),('name','ilike','Réserv%Termin')])
                elif vals['state'] == 'validated':
                    email_tmpl_id = email_obj.search(cr, uid, [('model','=',self._name),('name','ilike','Réserv%Valid%')])
                    #Search for product attaches to be added to email
                    prod_ids = []
                    for resa in self.browse(cr, uid, ids):
                        prod_ids.extend([line.reserve_product.id for line in resa.reservation_line])
                    if prod_ids:
                        cr.execute("select id, res_id from ir_attachment where res_id in %s and res_model=%s order by res_id", (tuple(prod_ids), 'product.product'))
                        #format sql return to concat attaches with each prod_id
                        for item in cr.fetchall():
                            prod_attaches.setdefault(item[1],[])
                            prod_attaches[item[1]].append(item[0])

                if email_tmpl_id:
                    if isinstance(email_tmpl_id, list):
                        email_tmpl_id = email_tmpl_id[0]
                    #generate mail and send it with optional attaches
                    for resa in self.browse(cr, uid, resa_ids_notif):
                        #link attaches of each product
                        attach_values = []
                        for line in resa.reservation_line:
                            if prod_attaches.has_key(line.reserve_product.id):
                                attach_values.extend([(4,attach_id) for attach_id in prod_attaches[line.reserve_product.id]])
                        #and link optional paramter attach_ids
                        attach_values.extend([(4,x) for x in attach_ids])
                        mail_id = email_obj.send_mail(cr, uid, email_tmpl_id, resa.id)
                        self.pool.get("mail.message").write(cr, uid, [mail_id], {'attachment_ids':attach_values})
                        self.pool.get("mail.message").send(cr, uid, [mail_id])

        return True

    """
    @param prod_dict: [{prod_id:id,qty_desired:qty}] a dict mapping prod and corresponding qty desired to check
    @param checkin: str containg begining date of the range of the check
    @param checkout: str containg ending date of the range of the check
    @return: list of dates of unaivalability : [('checkin1','checkout1'),('checkin2','checkout2')]
    @note: to be used in xmlrpc context only
    """
    def get_unaivailable_dates(self, cr, uid, prod_dict, checkin, checkout,context=None):
        #first, get reservation belonging to prod_ids and being in the range (checkin,chekout)
        prod_ids = [item['prod_id'] for item in prod_dict]
        resa_ids = self.search(cr, uid, [('reservation_line.reserve_product.id','in',prod_ids),'|',
                                             '&',('checkin','>=',checkin),('checkin','<=',checkout),
                                             '&',('checkout','>=',checkin),('checkout','<=',checkout)],order='checkin',context=context)

        #i store all checkin - checkout in dates_limit, i order this list,
        #and then, i'll have all dates delimiting (checkin-checkout) checks of qty
        dates_limit = []
        for resa in self.read(cr, uid, resa_ids, ['checkin','checkout']):
            if resa['checkin'] not in dates_limit:
                dates_limit.append(resa['checkin'])
            if resa['checkout'] not in dates_limit:
                dates_limit.append(resa['checkout'])
        dates_limit.sort()
        dates_check = []
        #now, i generate all (checkin-checkout) couple to test
        #for example: dates_limit=[date_a,date_b,date_c] => dates_check=[(date_a,date_b),(dateb,date_c)]
        for i in range(len(dates_limit) - 1):
            dates_check.append((dates_limit[i],dates_limit[i+1]))
        #and i get prod_qty for each date_check,
        #if, for one prod_id, qty is not sufficient, add date_check to the returned value
        ret = []
        for checkin,checkout in dates_check:
            prod_reserved = self.get_prods_available_and_qty(cr, uid, checkin, checkout, prod_ids=prod_ids, context=None)
            for item in prod_dict:
                if item['qty_desired'] > prod_reserved[str(item['prod_id'])]:
                    ret.append((checkin,checkout))
                    #date computed as unavailable, we can skip other prod_id tests for this date
                    break
        return ret

hotel_reservation()

class openresa_reservation_choice(osv.osv):
    _name = "openresa.reservation.choice"

    """
    @param ids: ids of record to compute value
    @return: if all lines are 'dispo' and without 'conflict', returns available
            elif all lines are 'dispo' but if some are 'conflict', returns conflict
            else returns unavailable (some line are not 'dispo')
    @note: can not use fields of hotel.reservation as it, because it changes the checkin-checkout for each choice
    """
    def _get_choice_dispo(self, cr, uid, ids, name, args, context=None):
        #by default, returns available

        return ret

    _columns = {
        'checkin':fields.datetime('Checkin', required=True),
        'checkout':fields.datetime('Checkout', required=True),
        'sequence':fields.integer('Sequence', required=True),
        'state':fields.selection([('waiting','Available choice'),('choosen','Choosen choice'),('refused','Refused choice')]),
        'reservation_id':fields.many2one('hotel.reservation','Reservation'),
        'dispo':fields.function(_get_choice_dispo, type="selection", selection=[('conflict','Conflict'),('unavailable','Unavailable'),('available','Available')], method=True, string="Dispo",),
        }
    _order = "sequence"
    _defaults = {
            'state':lambda *a: 'waiting',
        }
    #override create method to force seconds of dates to '00'
    def create(self, cr, uid, vals, context=None):
        if 'checkin' in vals:
            if len(vals['checkin']) > 16:
                vals['checkin'] = vals['checkin'][0:16] + ':00'
        if 'checkout' in vals:
            if len(vals['checkout']) > 16:
                vals['checkout'] = vals['checkout'][0:16] + ':00'
        return super(openstc_reservation_choice,self).create(cr, uid, vals, context=context)

    #override write method to force seconds of dates to '00'
    def write(self, cr, uid, ids, vals, context=None):
        if 'checkin' in vals:
            if len(vals['checkin']) > 16:
                vals['checkin'] = vals['checkin'][0:16] + ':00'
        if 'checkout' in vals:
            if len(vals['checkout']) > 16:
                vals['checkout'] = vals['checkout'][0:16] + ':00'
        return super(openstc_reservation_choice, self).write(cr, uid, ids, vals, context=context)

openresa_reservation_choice()

class product_category(osv.osv):
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

class purchase_order(osv.osv):
    _inherit = "purchase.order"
    _name = "purchase.order"
    _columns = {'is_emprunt':fields.boolean('Demande d\'emprunt', help="Indique qu'il s'agit d'une demande d'emprunt aurpès d'une mairie extèrieure et non d'un bon de commande")}
    _defaults = {
                 'is_emprunt':lambda *a: 0,
                 }

    def emprunt_done(self, cr, uid, ids):
        self.write(cr, uid, ids, {'state':'done'})
        return True

    #Force purchase.order workflow to cancel its pickings (subflow returns cancel and reactivate workitem at picking activity)
    def do_terminate_emprunt(self, cr, uid, ids, context=None):
        list_picking_ids = []
        wf_service = netsvc.LocalService('workflow')
        for purchase in self.browse(cr, uid, ids):
            for picking in purchase.picking_ids:
                wf_service.trg_validate(uid, 'stock.picking', picking.id, 'button_cancel', cr)
            wf_service.trg_write(uid, 'purchase.order', purchase.id, cr)

        return {
                'res_model':'purchase.order',
                'type:':'ir.actions.act_window',
                'view_mode':'form',
                'target':'current',
                }
purchase_order()

class sale_order(osv.osv):
    _inherit = "sale.order"
    _name = "sale.order"

    #TODO: create custom jasper report instead of classic pdf report
    def _create_report_attach(self, cr, uid, record, context=None):
        #sources insipered by _edi_generate_report_attachment of EDIMIXIN module
        ir_actions_report = self.pool.get('ir.actions.report.xml')
        matching_reports = ir_actions_report.search(cr, uid, [('model','=',self._name),
                                                              ('report_type','=','pdf')])
        ret = False
        if matching_reports:
            report = ir_actions_report.browse(cr, uid, matching_reports[0])
            report_service = 'report.' + report.report_name
            service = netsvc.LocalService(report_service)
            (result, format) = service.create(cr, uid, [record.id], {'model': self._name}, context=context)
            eval_context = {'time': time, 'object': record}
            if not report.attachment or not eval(report.attachment, eval_context):
                # no auto-saving of report as attachment, need to do it manually
                result = base64.b64encode(result)
                file_name = record.name_get()[0][1]
                file_name = re.sub(r'[^a-zA-Z0-9_-]', '_', file_name)
                file_name += ".pdf"
                ir_attachment = self.pool.get('ir.attachment').create(cr, uid,
                                                                      {'name': file_name,
                                                                       'datas': result,
                                                                       'datas_fname': file_name,
                                                                       'res_model': self._name,
                                                                       'res_id': record.id},
                                                                      context=context)
                ret = ir_attachment
        return ret

sale_order()

class account_invoice(osv.osv):
    _inherit = "account.invoice"
    _name = "account.invoice"

    _columns = {
        }

        #TODO: create custom jasper report instead of classic pdf report
    def _create_report_attach(self, cr, uid, record, context=None):
        #sources insipered by _edi_generate_report_attachment of EDIMIXIN module
        ir_actions_report = self.pool.get('ir.actions.report.xml')
        matching_reports = ir_actions_report.search(cr, uid, [('model','=',self._name),
                                                              ('report_type','=','pdf')])
        ret = False
        if matching_reports:
            report = ir_actions_report.browse(cr, uid, matching_reports[0])
            report_service = 'report.' + report.report_name
            service = netsvc.LocalService(report_service)
            (result, format) = service.create(cr, uid, [record.id], {'model': self._name}, context=context)
            eval_context = {'time': time, 'object': record}
            if not report.attachment or not eval(report.attachment, eval_context):
                # no auto-saving of report as attachment, need to do it manually
                result = base64.b64encode(result)
                file_name = record.name_get()[0][1]
                file_name = re.sub(r'[^a-zA-Z0-9_-]', '_', file_name)
                file_name += ".pdf"
                ir_attachment = self.pool.get('ir.attachment').create(cr, uid,
                                                                      {'name': file_name,
                                                                       'datas': result,
                                                                       'datas_fname': file_name,
                                                                       'res_model': self._name,
                                                                       'res_id': record.id},
                                                                      context=context)
                ret = ir_attachment
        return ret

    #override to force creation of pdf report (base function (ir.actions.server) was unlinked and replaced by this one)
    def action_number(self, cr, uid, ids, context=None):
        res = super(account_invoice, self).action_number(cr, uid, ids, context)
        for inv in self.browse(cr, uid, ids, context):
            report_attach = self._create_report_attach(cr, uid, inv, context)
        return res

account_invoice()

class res_partner(osv.osv):
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
