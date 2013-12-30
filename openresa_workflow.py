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

class hotel_reservation(osv.osv):
    _inherit = "hotel.reservation"
    
    """ @note: OpenERP Workflow method, send email notification, generate 'invoicing' report 
        and add it to email if 'send_invoicing' field is True """
    def confirmed_reservation(self,cr,uid,ids):
        for resa in self.browse(cr, uid, ids):
            if self.is_all_dispo(cr, uid, ids[0]):
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
    
    """@note: OpenERP Workflow method, send mail notification"""
    def waiting_confirm(self, cr, uid, ids):
        if self.is_all_dispo(cr, uid, ids[0]):
            self.envoyer_mail(cr, uid, ids, {'state':'waiting'})
            self.write(cr, uid, ids, {'state':'wait_confirm'})
            return True
        raise osv.except_osv(_("""Not available"""),_("""Not all of your products are available on those quantities for this period"""))
        return False
    
    """@note: OpenERP Workflow method, send mail notification"""
    def cancelled_reservation(self, cr, uid, ids):
        self.envoyer_mail(cr, uid, ids, {'state':'error'})
        self.write(cr, uid, ids, {'state':'cancel'})
        return True

    """@note: OpenERP Workflow method, send mail notification"""
    def redrafted_reservation(self, cr, uid, ids):
        self.write(cr, uid, ids, {'state':'remplir'})
        return True
    
    """ @note: OpenERP Workflow method, send email notification, generate 'invoicing' report 
    and add it to email if 'send_invoicing' field is True """
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
    
    """ OpenERP workflow transition method to know if resa must be validated by manager or not.
    booking need validation if user is not manager and if lines.bookable.seuil_confirm < lines.qte_reserves """
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
        
    """@note: OpenERP Workflow method, send mail notification"""
    def ARemplir_reservation(self, cr, uid, ids):
        for resa in self.browse(cr, uid, ids):
            if resa.is_template or not resa.recurrence_id:
                self.envoyer_mail(cr, uid, ids, {'state':'waiting'})
        self.write(cr, uid, ids, {'state':'remplir'})
        return True
    
    """ OpenERP workflow transition method to know if resa can be validated or not.
    booking can be validated if lines.dispo is True or if lines.block_booking is False """
    def is_all_dispo(self, cr, uid, id, context=None):
        for line in self.browse(cr, uid, id, context).reservation_line:
            if line.reserve_product.block_booking and not line.dispo:
                return False
        return True
    
hotel_reservation()