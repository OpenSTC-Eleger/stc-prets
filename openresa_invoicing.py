# -*- coding: utf-8 -*-

##############################################################################
#
#    OpenResa module for OpenERP, module OpenResa
#    Copyright (C) 200X Company (<http://website>) pyf
#
#    This file is a part of OpenResa
#
#    OpenResa is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    OpenResa is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
from osv import fields, osv
import netsvc
import time
import base64
import re
from datetime import datetime,timedelta
from datetime import datetime
from mx.DateTime.mxDateTime import strptime

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

class hotel_reservation_line(osv.osv):
    _inherit = "hotel_reservation.line"
    
    def _get_amount(self, cr, uid, ids, name, args, context=None):
        ret = {}.fromkeys(ids, 0.0)
        for line in self.browse(cr, uid, ids, context):
            amount = line.pricelist_amount * line.qte_reserves
            ret.update({line.id:amount})
            #TOCHECK: is there any taxe when collectivity invoice people ?
        return ret
    
    _columns = {
        'pricelist_amount':fields.float('Price from pricelist'),
        'pricelist_item':fields.many2one('product.pricelist.item','Pricelist item of invoicing'),
        'uom_qty':fields.float('Qté de Référence pour Facturation',digit=(2,1)),
        'amount':fields.function(_get_amount, string="Prix (si tarifé)", type="float", method=True, store=False),
        
        }
    
hotel_reservation_line()

class hotel_reservation(osv.osv):
    _inherit = "hotel.reservation"
    
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
        'amount_total': fields.function(_get_amount_total, type='float', string='Amount Total', method=True,
                multi="resa",
                help='Optionnal, if positive, a sale order will be created once resa validated and invoice will be created once resa done.'),
        'all_dispo': fields.function(_get_amount_total, type="boolean", string="All Dispo", method=True, multi="resa"),
        'confirm_note': fields.text('Note de validation'),
        'cancel_note': fields.text('Note de refus'),
        'done_note': fields.text('Note de clôture'),
        'send_invoicing': fields.boolean('Send invoicing by email'),
        'invoice_attachment_id': fields.integer('Attachment ID'),
        }
    
    
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
    
    """
    @param checkin: datetime start of booking
    @param checkout: datetime end of booking
    @return: length of booking in hour (hour is the default uom for booking pricing)
    """
    def get_length_resa(self, cr, uid, checkin, checkout, context=None):
        checkin = strptime(checkin, '%Y-%m-%d %H:%M:%S')
        checkout = strptime(checkout, '%Y-%m-%d %H:%M:%S')
        length = (checkout - checkin).hours
        return length


    """
    @param product_id: id of bookable to retrieve pricing
    @param uom_qty: qty computed by get_length_resa used to get pricelist_item
    @param partner_id: id of claimer, used to retrieve pricelist_item
    @param pricelist_id: optional param to replace default partner pricelist
    @return: pricing of booking (float) if found, else False
    """
    def get_prod_price(self, cr, uid, product_id, uom_qty, partner_id, pricelist_id=False, context=None):
        pricelist_obj = self.pool.get("product.pricelist")
        if not pricelist_id:
            pricelist_id = self.pool.get('res.partner').browse(cr, uid, partner_id, context=context).property_product_pricelist.id
        res = pricelist_obj.price_get_multi(cr, uid, [pricelist_id], [(product_id,uom_qty,partner_id)], context=None)
        return res and (res[product_id][pricelist_id]) or False

    """
    @note: OpenERP internal invoicing compute, retrieve uom_qty (based on booking_length in hour and bookable.uom_id) 
            and pricing (using pricelist filled in booking, default is partner-pricelist)
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
    
hotel_reservation()