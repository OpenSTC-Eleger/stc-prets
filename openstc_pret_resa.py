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
        #TOCHECK: Is service_technical_id usefull now ?
        'service_technical_id':fields.many2one('openstc.service', 'Service Technique associé',help='Si renseigné, indique que cette ressource nécessite une manipulation technique pour être installée sur site, cette ressource est donc susceptible de générer une intervention sur ce service.'),
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
    def get_bookables(self, cr, uid, claimer_user_id=False, claimer_partner_id=False, context=None):
        prod_ids = []
        equipment_obj = self.pool.get("openstc.equipment")
        site_obj = self.pool.get("openstc.site")
        equipments = []
        sites = []
        domain = []
        #if it's an user, prod_ids are filtered according to 'internal' reservable rights
        if claimer_user_id and not claimer_partner_id:
            user = self.pool.get("res.users").read(cr, uid, claimer_user_id, ['service_ids'],context=context)
            domain = [('internal_booking','=',True),'|',
                      ('service_bookable_ids.id','child_of',[service_id for service_id in user['service_ids']]),
                      ('service_bookable_ids','=',False)]
        #else, if it's a partner, prod_ids are filtered according to 'external' reservable rights
        elif not claimer_user_id and claimer_partner_id:
            partner = self.pool.get('res.partner').read(cr, uid, claimer_partner_id, ['type_id'],context=context)
            domain = [('external_booking','=',True),'|',
                      ('partner_type_bookable_ids','child_of',partner['type_id'] and partner['type_id'][0] or []),
                      ('partner_type_bookable_ids','=',False)]
        #else, if both partner and user id are supplied, or no one of them, raise an error
        else:
            osv.except_osv(_('Error'),_('Incorrect values, you have to supply one and only one between claimer_user_id or claimer_partner_id, not both'))

        #retrieve values for equipments and sites authorized
        equipment_ids = equipment_obj.search(cr, uid, domain, context=context)
        equipments = equipment_obj.read(cr, uid, equipment_ids, ['product_product_id'], context=context)
        site_ids = site_obj.search(cr, uid, domain, context=context)
        sites = site_obj.read(cr, uid, site_ids, ['product_id'], context=context)

        #finally, compute results by merging 'product.product' many2ones of
        #records from tables openstc.equipment and openstc.site
        prod_ids.extend([elt['product_product_id'] for elt in equipments if elt['product_product_id']])
        prod_ids.extend([elt['product_id'] for elt in sites if elt['product_id']])
        return prod_ids

product_product()


class hotel_reservation_line(osv.osv):
    _name = "hotel_reservation.line"
    _inherit = "hotel_reservation.line"

    _AVAILABLE_ACTION_VALUES = [('nothing','Pas d\'intervention'),('inter','Intervention à générer'),('inter_ok','Intervention générée')]

    def name_get(self, cr, uid, ids, context=None):
        ret = []
        for line in self.browse(cr, uid, ids, context):
            ret.append((line.id,'%s %s' % (line.qte_reserves, line.reserve_product)))
        return ret
    #@tocheck: useless ?
    #Ligne valide si (infos XOR no_infos)
    def _calc_line_is_valid(self, cr, uid, ids, name, args, context=None):
        ret = {}
        for line in self.browse(cr, uid, ids):
            ret.update({line.id: (line.infos and not line.no_infos) or (not line.infos and line.no_infos)})
        return ret
    #@tocheck: useless ?
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
                    ret.update({line.id:{'qte_dispo':available[line.reserve_product.id]}})
                    if 'dispo' in name:
                        ret[line.id].update({'dispo':available[line.reserve_product.id] >= line.qte_reserves})
        elif 'dispo' in name:
            for line in self.browse(cr, uid, ids):
                ret.update({line.id:{'dispo':line.qte_dispo >= line.qte_reserves}})
        return ret

    def _get_amount(self, cr, uid, ids, name, args, context=None):
        ret = {}.fromkeys(ids, 0.0)
        for line in self.browse(cr, uid, ids, context):
            amount = line.prix_unitaire * line.uom_qty * line.qte_reserves
            ret[line.id] = amount
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
            #if weekday_start == weekday_end:
                #date_str = '%s %s-%s : ' %(weekday_to_str[weekday_start],line.checkin[11:16],line.checkout[11:16])

            if weekday_start <> weekday_end:
                date_str = '%s %s - %s %s : ' % (weekday_to_str[weekday_start][:3],checkin[11:16],weekday_to_str[weekday_end][:3],checkout[11:16])
            ret[line.id] = '%s %d x %s (%s)' %(date_str,line.qte_reserves, line.reserve_product.name_template, line.partner_id.name)
        return ret

    ''' get conflicting lines for each reservation 's line'''
    def _get_conflicting_lines(self, cr, uid, ids, name, args, context=None):
        conflicting_lines = {}
        #for each line
        for line in self.browse(cr, uid, ids, context=context):
            conflicting_lines[line.id] = []
            temp_lines = []
            sum_qty = 0
            if line.line_id.id != False and line.reserve_product.id != False and line.checkin!=False and line.checkout!=False:
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
        "prix_unitaire": fields.float("Prix Unitaire", digit=(4,2)),
        'dispo':fields.function(_calc_qte_dispo, string="Disponible", method=True, multi="dispo", type='boolean'),
        "infos":fields.char("Informations supplémentaires",size=256),
        "name":fields.char('Libellé', size=128),
        'state':fields.related('line_id','state', type='selection',string='Etat Résa', selection=_get_state_line, readonly=True),
        'uom_qty':fields.float('Qté de Référence pour Facturation',digit=(2,1)),
        'amount':fields.function(_get_amount, string="Prix (si tarifé)", type="float", method=True),
        'qte_dispo':fields.function(_calc_qte_dispo, method=True, string='Qté Dispo', multi="dispo", type='float'),
        'action':fields.selection(_AVAILABLE_ACTION_VALUES, 'Action'),
        'state':fields.related('line_id','state', type='char'),
        'partner_id':fields.related('line_id','partner_id', type="many2one", relation="res.partner"),
        'checkin':fields.related('line_id','checkin', type="datetime"),
        'checkout':fields.related('line_id','checkout', type="datetime"),
        'resa_name':fields.related('line_id','name',type="char"),
        'complete_name':fields.function(_get_complete_name, type="char", string='Complete Name', size=128),
        'conflicting_lines':fields.function(_get_conflicting_lines, type='many2many', relation='hotel.reservation.lines',string='Conflicting rows'),


        }

    _defaults = {
     'qte_reserves':lambda *a: 1,
     'state':'remplir',
     'action':'nothing',
        }

    #@TOCHECK: useless ?
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

hotel_reservation_line()

class hotel_reservation(osv.osv):
    AVAILABLE_IN_OPTION_LIST = [('no','Rien à Signaler'),('in_option','Réservation En Option'),('block','Réservation bloquée')]
    _name = "hotel.reservation"
    _inherit = "hotel.reservation"
    _description = "Réservations"

    def remove_accents(self, str):
        return ''.join(x for x in unicodedata.normalize('NFKD',str) if unicodedata.category(x)[0] == 'L')

    def _custom_sequence(self, cr, uid, context):
        seq = self.pool.get("ir.sequence").next_by_code(cr, uid, 'resa.number',context)
        user = self.pool.get("res.users").browse(cr, uid, uid)
        prog = re.compile('[Oo]pen[a-zA-Z]{3}/[Mm]anager')
        service = False
        if 'service_id' in context:
            #get service_id in context, it takes priority to any other service
            service = context['service_id']
            service = self.pool.get("openstc.service").browse(cr, uid, service)
        else:
            #get first service_ids of user if the user is a manager
            for group in user.groups_id:
                if prog.search(group.name):
                    if isinstance(user.service_ids, list) and not service:
                        service = user.service_ids and user.service_ids[0] or False

        if service:
            #If sequence is configured to have service info, we write it
            seq = seq.replace('xxx',self.remove_accents(service.name[:3]).upper())

        return seq
    #@tocheck: useless ?
    def _calc_in_option(self, cr, uid, ids, name, args, context=None):
        print("start calc_in_option method")
        ret = {}
        #fixes : calc only for resa, avoiding inheritance bugs
        for resa in self.pool.get("hotel.reservation").browse(cr, uid, ids, context):
            ret[resa.id] = 'no'
            date_crea = strptime(resa.date_order, '%Y-%m-%d %H:%M:%S')
            checkin = strptime(resa.checkin, '%Y-%m-%d %H:%M:%S')
            for line in resa.reservation_line:
                #Vérif si résa dans les délais, sinon, in_option est cochée
                d = timedelta(days=int(line.reserve_product.sale_delay and line.reserve_product.sale_delay or 0))
                print("now :"+str(date_crea))
                print("checkin :" + str(checkin))
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
        return [('draft', 'Saisie des infos personnelles'),('confirm','Réservation confirmée'),('cancle','Annulée'),('in_use','Réservation planifiée'),('done','Réservation Terminée'), ('remplir','Saisie de la réservation'),('wait_confirm','En Attente de Confirmation')]

    def _get_state_values(self, cr, uid, context=None):
        return self.return_state_values(cr, uid, context)

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

    _columns = {
                'state': fields.selection(_get_state_values, 'Etat',readonly=True),
                'in_option':fields.function(_calc_in_option, string="En Option", selection=AVAILABLE_IN_OPTION_LIST, type="selection", method = True, store={'hotel.reservation':(get_resa_modified,['checkin','reservation_line'],10)},
                                            help=("Une réservation mise en option signifie que votre demande est prise en compte mais \
                                            dont on ne peut pas garantir la livraison à la date prévue.\
                                            Une réservation bloquée signifie que la réservation n'est pas prise en compte car nous ne pouvons pas \
                                            garantir la livraison aux dates indiquées")),
                'name':fields.char('Nom Manifestation', size=128, required=True),
                'partner_mail':fields.char('Email Demandeur', size=128, required=False),
                'is_recur':fields.boolean('Issue d\'une Récurrence', readonly=True),
                'site_id':fields.many2one('openstc.site','Site (Lieu)'),
                'prod_id':fields.many2one('product.product','Ressource'),
                'openstc_partner_id':fields.many2one('res.partner','Demandeur', help="Personne demandant la réservation."),
                'resa_checkout_id':fields.many2one('openstc.pret.checkout','Etat des Lieux associé'),
                'amount_total':fields.function(_get_amount_total, type='float', string='Amount Total', method=True, multi="resa",
                                               help='Optionnal, if positive, a sale order will be created once resa validated and invoice will be created once resa done.'),
                'all_dispo':fields.function(_get_amount_total, type="boolean", string="All Dispo", method=True, multi="resa"),
        }
    _defaults = {
                 'in_option': lambda *a :0,
                 'state': lambda *a: 'remplir',
                 'is_recur': lambda *a: 0,
                 'reservation_no': lambda self,cr,uid,ctx=None:self._custom_sequence(cr, uid, ctx),
        }
    _order = "checkin, in_option"

    def _check_dates(self, cr, uid, ids, context=None):
        for resa in self.browse(cr, uid, ids, context):
            if resa.checkin >= resa.checkout:
                return False
        return True

    _constraints = [(_check_dates, _("Your checkin is greater than your checkout, please modify them"), ['checkin','checkout'])]


    def create(self, cr, uid, vals, context=None):
        #Si on vient de créer une nouvelle réservation et qu'on veut la sauvegarder (cas où l'on appuie sur
        #"vérifier disponibilités" juste après la création (openERP force la sauvegarde)
        #Dans ce cas, on mets des valeurs par défauts pour les champs obligatoires
        #print(vals)
        if not 'state' in vals or vals['state'] == 'remplir':
            vals['shop_id'] = self.pool.get("sale.shop").search(cr, uid, [], limit=1)[0]
        if 'checkin' in vals:
            if len(vals['checkin']) > 10:
                vals['checkin'] = vals['checkin'][:-3] + ':00'
        if 'checkout' in vals:
            if len(vals['checkout']) >10:
                vals['checkout'] = vals['checkout'][:-3] + ':00'
        return super(hotel_reservation, self).create(cr, uid, vals, context)

    def write(self, cr, uid, ids, vals, context=None):
        #if dates are modified, we uncheck all dispo to force user to re check all lines
        if context == None:
            context = {}
        if 'checkin' in vals:
            if len(vals['checkin']) > 10:
                vals['checkin'] = vals['checkin'][:-3] + ':00'
        if 'checkout' in vals:
            if len(vals['checkout']) >10:
                vals['checkout'] = vals['checkout'][:-3] + ':00'
        res = super(hotel_reservation, self).write(cr, uid, ids, vals, context)
        #if 'checkin' in vals or 'checkout' in vals:
        #    self.trigger_reserv_modified(cr, uid, ids, context)
        return res

    def unlink(self, cr, uid, ids, context=None):
        if not isinstance(ids, list):
            ids = [ids]
        line_ids = []
        for resa in self.browse(cr, uid, ids, context):
            line_ids.extend([x.id for x in resa.reservation_line])
        self.pool.get("hotel_reservation.line").unlink(cr, uid, line_ids, context)
        return super(hotel_reservation, self).unlink(cr, uid, ids, context)

    def onchange_in_option(self, cr, uid, ids, in_option=False, state=False, context=None):
        #TOREMOVE:
        #if in_option:
            #Affichage d'un wizard pour simuler une msgbox
        if in_option:
            return {'warning':{'title':'Réservation mise en option', 'message': '''Attention, Votre réservation est "hors délai"
            , nous ne pouvons pas vous assurer que nous pourrons vous livrer.'''}}

        return {'value':{}}

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
                #TOCHECK: as long as form is written by employee, we let him all latitude to manage prices
                #Calcul montant de la résa
                form_amount = 0.0
                line_ids = []
                for line in resa.reservation_line:
                    form_amount += line.prix_unitaire * line.qte_reserves
                if form_amount > 0.0:
                #Si montant > 0 euros, générer sale order puis dérouler wkf jusqu'a édition facture
                    folio_id = self.create_folio(cr, uid, ids)
                    wf_service = netsvc.LocalService('workflow')
                    wf_service.trg_validate(uid, 'hotel.folio', folio_id, 'order_confirm', cr)
                    folio = self.pool.get("hotel.folio").browse(cr, uid, folio_id)
                    move_ids = []
                    for picking in folio.order_id.picking_ids:
                        for move in picking.move_lines:
                            #On crée les mvts stocks inverses pour éviter que les stocks soient impactés
                            self.pool.get("stock.move").copy(cr, uid, move.id, {'picking_id':move.picking_id.id,'location_id':move.location_dest_id.id,'location_dest_id':move.location_id.id,'state':'draft'})
                    #On mets a jour le browse record pour qu'il intégre les nouveaux stock moves
                    folio.refresh()
                    #On applique et on termine tous les stock moves (ceux créés de base par sale order et ceux créés ce dessus
                    for picking in folio.order_id.picking_ids:
                        move_ids.extend([x.id for x in picking.move_lines])
                    self.pool.get("stock.move").action_done(cr, uid, move_ids)
                    attach_sale_id.append(self.pool.get("sale.order")._create_report_attach(cr, uid, folio.order_id))
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

    #Mettre à l'état cancle et retirer les mouvements de stocks (supprimer mouvement ou faire le mouvement inverse ?)
    def cancelled_reservation(self, cr, uid, ids):
        self.write(cr, uid, ids, {'state':'cancle'})
        return True

    def drafted_reservation(self, cr, uid, ids):
        for resa in self.browse(cr, uid, ids):
            if self.is_all_dispo(cr, uid, ids[0]):
                if resa.in_option == 'block':
                    raise osv.except_osv(_("Error"),_("""Your resa is blocked because your expected date is too early so that we can not supply your products at time"""))
                if not resa.reservation_line:
                    raise osv.except_osv("Error","You have to write at least one reservation line")
                self.write(cr, uid, ids, {'state':'draft'})
                #TODO: Si partner_shipping_id présent, calculer prix unitaires
                if resa.openstc_partner_id:
                    self.compute_lines_price(cr, uid, [resa.id])
                return True
            else:
                raise osv.except_osv(_("""Not available"""),_("""Not all of your products are available on those quantities for this period"""))
                return False
        return True

    def redrafted_reservation(self, cr, uid, ids):
        self.write(cr, uid, ids, {'state':'remplir'})
        return True
    def in_used_reservation(self, cr, uid, ids):
        self.put_in_use_with_intervention(cr, uid, ids)
        self.write(cr, uid, ids, {'state':'in_use'})
        return True
    def done_reservation(self, cr, uid, ids):
        if isinstance(ids, list):
            ids = ids[0]
        resa = self.browse(cr, uid, ids)
        if resa.is_recur:
            #TODO: create invoice from scratch
            pass
        else:
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
            if inv_ids:
                #attaches = self.pool.get("ir.attachment").search(cr, uid, [('res_model_','=','account.invoice'),('res_id','in',inv_ids)])
                cr.execute("select id from ir_attachment where res_model = %s and res_id in %s", ('account.invoice',tuple(inv_ids)))
                attaches = [item[0] for item in cr.fetchall()]
                if not isinstance(attaches, list):
                    attaches = [attaches]
                self.envoyer_mail(cr, uid, [ids], vals={'state':'done'}, attach_ids=attaches)
        self.write(cr, uid, ids, {'state':'done'})
        return True
    def is_drafted(self, cr, uid, ids):
        for values in self.browse(cr, uid, ids):
            if values.state <> 'draft':
                return False
        return True

    def is_not_drafted(self, cr, uid, ids):
        return not self.is_drafter
    #@todo: change openstc_manager for hotel.group_manager group
    def need_confirm(self, cr, uid, ids):
        reservations = self.browse(cr, uid, ids)
        etape_validation = False
        #if group == "Responsable", no need confirm
        group_manager_id = self.pool.get("ir.model.data").get_object_reference(cr, uid, 'openbase','openstc_manager')
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
    #@tocheck: useless ?
    def not_need_confirm(self, cr, uid, ids):
        return not self.need_confirm(cr, uid, ids)

    def ARemplir_reservation(self, cr, uid, ids):
        #TOCHECK: Voir quand il faut mettre la résa à l'état "in_option" : Clique sur Suivant malgré non dispo ?
        self.write(cr, uid, ids, {'state':'remplir'})
        return True

    #Fonction (liée à une action) permettant de pré-remplir la fiche de réservation en fonction des infos du ou des articles sélectionnés
    def default_get(self, cr, uid, fields, context=None):
        res = super(hotel_reservation, self).default_get(cr, uid, fields, context=context)
        #Si pour l'initialisation de la vue, on est passé par l'action "Réserver article(s)" associée aux catalogues produits
        if ('from_product' in context) and (context['from_product']=='1') :
            data = context and context.get('product_ids', []) or []
            produit_obj = self.pool.get('product.product')
            #produit_obj = self.pool.get('hotel.room')
            #Pour chaque produit sélectionnés dans la vue tree des catalogues, on crée une ligne de réservation (objet hotel.reservation.line)
            reservation_lines = []
            for produit in produit_obj.browse(cr, uid, data, []):
                reservation_lines.append(self.pool.get('hotel_reservation.line').create(cr, uid, {
                                                                                        'reserve_product':  produit.id,
                                                                                        'categ_id':produit.categ_id.id,
                                                                                        'reserve':[(4, produit.id)],
                                                                                        'prix_unitaire':produit.product_tmpl_id.list_price,
                                                                                        'qte_reserves':1.0
                                                                                }))

            res.update({'reservation_line':reservation_lines})
        #Valeurs par défauts des champs cachés
        return res

    def get_nb_prod_reserved(self, cr, prod_list, checkin, checkout, states=['cancle','done','remplir'], where_optionnel=""):
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
    def get_prods_available_and_qty(self, cr, uid, checkin, checkout, prod_ids=[], where_optionnel='', context=None):
        #if no prod_ids put, we check all prods
        if not prod_ids:
            prod_ids = self.pool.get("product.product").search(cr, uid, [])
        prods = self.pool.get("product.product").browse(cr, uid, prod_ids)
        prod_dispo = {}
        #by default, all qty in stock are available
        for prod in prods:
            prod_dispo.setdefault(prod.id, prod.virtual_available)
        #and, if some resa are made to this prods, we substract default qty with all qty reserved at these dates
        results = self.get_nb_prod_reserved(cr, prod_ids, checkin, checkout, where_optionnel=where_optionnel).fetchall()
        for prod_id, qty_reserved in results:
            prod_dispo[prod_id] -= qty_reserved
        return prod_dispo

    #Vérifies les champs dispo de chaque ligne de résa pour dire si oui ou non la résa est OK pour la suite
    #TODO: Voir comment gérer le cas de la reprise d'une résa à revalider / incomplète où des champs dispo sont à True
    #=> Problème lorsque quelqu'un d'autre réserve un même produit
    def is_all_dispo(self, cr, uid, id, context=None):
        for line in self.browse(cr, uid, id, context).reservation_line:
            if not line.dispo:
                return False
        return True

    def is_all_valid(self, cr, uid, id, context=None):
        for line in self.browse(cr, uid, id, context).reservation_line:
            if not line.valide and line.reserve_product.need_infos_supp:
                return False
        return True

    #polymorphism of _create_folio
    def create_folio(self, cr, uid, ids, context=None):
        for reservation in self.browse(cr,uid,ids):
            room_lines = []
            for line in reservation.reservation_line:
                room_lines.append((0,0,{
                   'checkin_date':reservation['checkin'],
                   'checkout_date':reservation['checkout'],
                   'product_id':line.reserve_product.id,
                   'name':line.reserve_product.name_template,
                   'product_uom':line.reserve_product.uom_id.id,
                   'price_unit':line.prix_unitaire,
                   'product_uom_qty':line.uom_qty

                   }))
            folio=self.pool.get('hotel.folio').create(cr,uid,{
                  'date_order':reservation.date_order,
                  'shop_id':reservation.shop_id.id,
                  'partner_id':reservation.partner_id.id,
                  'pricelist_id':reservation.pricelist_id.id,
                  'partner_invoice_id':reservation.partner_invoice_id.id,
                  'partner_order_id':reservation.partner_order_id.id,
                  'partner_shipping_id':reservation.partner_shipping_id.id,
                  'checkin_date': reservation.checkin,
                  'checkout_date': reservation.checkout,
                  'room_lines':room_lines,
           })
            cr.execute('insert into hotel_folio_reservation_rel (order_id,invoice_id) values (%s,%s)', (reservation.id, folio))

        return folio

    #param record: browse_record hotel.reservation.line
    def get_prod_price(self, cr, uid, ids, record, context=None):
        pricelist_obj = self.pool.get("product.pricelist")
        pricelist_id = record.line_id.pricelist_id.id
        if not pricelist_id:
            pricelist_id = record.line_id.partner_id.property_product_pricelist.id
        res = pricelist_obj.price_get_multi(cr, uid, [pricelist_id], [(record.reserve_product.id,record.uom_qty,record.line_id.partner_id.id)], context=None)
        return res and res[record.reserve_product.id][pricelist_id] or False
        #return record.reserve_product.product_tmpl_id.standard_price

    #param record: browse_record hotel.reservation.line
    #if product uom refers to a resa time, we compute uom according to checkin, checkout
    def get_prod_uom_qty(self, cr, uid, ids, record, length, context=None):
        if re.search(u"([Tt]emporel|[Rr][ée]servation)", record.reserve_product.uom_id.category_id.name):
            #uom factor refers to day, to have uom factor refering to hours, we have to adjust ratio
            factor = 24.0 / record.reserve_product.uom_id.factor
            res = length / factor
            #round to direct superior int
            #TODO: here we can apply an adjustment to decide the max decimal value before passing to superior int
            if res > int(res):
                res = int(res) + 1.0
        else:
            res = record.qte_reserves
        return res

    def get_length_resa(self, cr, uid, id, context=None):
        resa = self.browse(cr, uid, id, context)
        checkin = strptime(resa.checkin, '%Y-%m-%d %H:%M:%S')
        checkout = strptime(resa.checkout, '%Y-%m-%d %H:%M:%S')
        length = (checkout - checkin).hours
        return length

    def get_amount_resa(self, cr, uid, ids, context=None):
        pricelist_obj = self.pool.get("product.pricelist")
        for resa in self.browse(cr, uid, ids ,context):
            pricelist = resa.partner_id.property_product_pricelist.id
            amount = 0.0
            values = []
            for line in resa.reservation_line:
                #TOREMOVE: for each prod, gets price from table price
                #amount += self.get_prod_price(cr, uid, ids, line, context) * line.qte_reserves
                #TODO: for each prod, gets price from pricelist
                values.append((line.reserve_product.id,line.qte_reserves, resa.partner_id.id))
            pricelist_obj = self.pool.get("product.pricelist")
            res = pricelist_obj.price_get_multi(cr, uid, [pricelist], values, context=None)
            #compute amount with price_unit got
            for line in resa.reservation_line:
                amount += res[line.reserve_product.id][pricelist]
        return amount

    def compute_lines_price(self, cr, uid, ids, context=None):
        values = []
        #get lentgh resa in hours
        for resa in self.browse(cr, uid, ids, context):
            length_resa = self.get_length_resa(cr, uid, resa.id, context=None)
            values.extend([(1,line.id,{'prix_unitaire':self.get_prod_price(cr, uid, resa.id, line, context),
                                       'uom_qty':self.get_prod_uom_qty(cr, uid, resa.id, line, length_resa, context)}) for line in resa.reservation_line])
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



    #Vals: Dict containing "to" (deprecated) and "state" in ("error","draft", "confirm") (required)
    def envoyer_mail(self, cr, uid, ids, vals=None, attach_ids=[], context=None):
        #TODO: check if company wants to send email (info not(opt_out) in partner)
        #We keep only resa where partner have not opt_out checked
        resa_ids_notif = []
        resa_ids_notif = [resa.id for resa in self.browse(cr, uid, ids) if not resa.partner_id.opt_out]
        if resa_ids_notif:
            email_obj = self.pool.get("email.template")
            email_tmpl_id = 0
            prod_attaches = {}
            if 'state' in vals.keys():
                if vals['state'] == "error":
                    email_tmpl_id = email_obj.search(cr, uid, [('model','=',self._name),('name','ilike','annulée')])
                elif vals['state'] == 'validated':
                    email_tmpl_id = email_obj.search(cr, uid, [('model','=',self._name),('name','ilike','Réserv%Valid%')])
                    #Search for product attaches to be added to email
                    prod_ids = []
                    for resa in self.browse(cr, uid, ids):
                        prod_ids.extend([line.reserve_product.id for line in resa.reservation_line])
                    cr.execute("select id, res_id from ir_attachment where res_id in %s and res_model=%s order by res_id", (tuple(prod_ids), 'product.product'))
                    #format sql return to concat attaches with each prod_id

                    for item in cr.fetchall():
                        prod_attaches.setdefault(item[1],[])
                        prod_attaches[item[1]].append(item[0])
                elif vals['state'] == 'waiting':
                    email_tmpl_id = email_obj.search(cr, uid, [('model','=',self._name),('name','ilike','Réserv%Attente')])
                elif vals['state'] == 'done':
                    email_tmpl_id = email_obj.search(cr, uid, [('model','=',self._name),('name','ilike','Réserv%Termin')])
                if email_tmpl_id:
                    if isinstance(email_tmpl_id, list):
                        email_tmpl_id = email_tmpl_id[0]
                    #Envoi du mail proprement dit, email_tmpl_id définit quel mail sera envoyé
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

        return

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
                if item['qty_desired'] > prod_reserved[item['prod_id']]:
                    ret.append((checkin,checkout))
                    #date computed as unavailable, we can skip other prod_id tests for this date
                    break
        return ret

hotel_reservation()


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
    @param prod_ids_and_qties: list of tuples containing each prod_id - qty to retrieve their prices
    @param pricelist_id: id of the pricelist to retrieve prices
    @return: list of dict [{'prod_id':id, price:float_price}] according to pricelist_id correctly formated
    (instead of original methods of this nasty OpenERP)
    """
    def get_bookable_prices(self, cr, uid, partner_id, prod_ids_and_qties, pricelist_id=False, context=None):
        if not pricelist_id:
            pricelist_id = self.pool.get("res.partner").read(cr, uid, partner_id, ['property_product_pricelist'], context=context)['property_product_pricelist'][0]
        pricelist_obj = self.pool.get('product.pricelist')
        values = [(item[0],item[1], partner_id)for item in prod_ids_and_qties]
        #get prices from pricelist_obj
        res = pricelist_obj.price_get_multi(cr, uid, [pricelist_id], values, context=context)
        #format return to be callable by xmlrpc (because dict with integer on keys raises exceptions)
        ret = {}
        for key,val in res.items():
            ret.update({str(key):val[pricelist_id]})
        return ret
        
res_partner()
