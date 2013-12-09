# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2004-2010 Tiny SPRL (<http://tiny.be>).
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
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

import time
from report import report_sxw
from datetime import datetime

class openresa_folio_report(report_sxw.rml_parse):
    
    """
    @param order: sale_order browse_record of the report
    @return: returns only the same format of data : [{'prod':description,'qty':x, 'uom_qty':y, 'uom_name':name, 'unit_price':z, 'subtotal':x*y*z}]
    @note: if resa not in recurrence, returns each line where price > 0
        else returns line group by product_id where amount > 0 for each occurrence-line of recurrence
    """
    def get_lines(self,order):
        ret= {}
        #values of uom used for resa, if a prod has not uom_resa, we force it to display uom_day_resa
        data_obj = self.pool.get('ir.model.data')
        day_uom_id = data_obj.get_object_reference(self.cr, self.uid, 'openresa','openstc_pret_uom_day')[1]
        day_uom = self.pool.get('product.uom').browse(self.cr, self.uid, day_uom_id, context=self.localcontext)
        categ_uom_id = data_obj.get_object_reference(self.cr, self.uid, 'openresa','openstc_pret_uom_categ_resa')[1]
        #for each resa, merge values of all there lines
        for line in order.room_lines:
            if line.price_subtotal:
                #default value if prod not yet found (subtotal is computed at the end
                key = (line.product_id.id,line.product_uom_qty,line.product_uom.id,line.price_unit,line.discount)
                ret.setdefault(key, {'prod':line.product_id.name,
                                                     'uom_qty':int(line.product_uos_qty),
                                                     'uom_name':line.product_uos and line.product_uos.name or 'Date',
                                                     'unit_price':line.price_subtotal,
                                                     'discount':line.discount,
                                                     'description':line.product_id.description,
                                                     'dates':'',
                                                     'qty':0})
                #ret[key]['qty'] += int(line.product_uom_qty)
                ret[key]['dates'] += '\n %s - %s' % (self.formatLang(line.checkin_date,date_time=True)[0:16],self.formatLang(line.checkout_date,date_time=True)[0:16])
                ret[key]['qty'] += 1
                
        #format data to be easily used by report and to compute subtotal
        ret2 = []
        for key,val in ret.items():
            val.update({'subtotal':val['qty'] * val['unit_price']})
            ret2.append(val)
        
        return ret2
    
    def getResa(self, record):
        ret_ids = self.pool.get('hotel.reservation').search(self.cr, self.uid, [('folio_id.id','=',record.id)])
        ret = False 
        if ret_ids:
            ret = self.pool.get('hotel.reservation').browse(self.cr, self.uid, ret_ids[0],self.localcontext)
        return ret
    
    def __init__(self, cr, uid, name, context):
        super(openresa_folio_report, self).__init__(cr, uid, name, context)
        self.localcontext.update({
            'time': time,
            'datetime':datetime,
            'getLines':self.get_lines,
            'getResa':self.getResa,
        })

report_sxw.report_sxw('report.openresa.folio.report', 'hotel.folio',
      'addons/openresa/report/openresa_folio_report.rml', parser=openresa_folio_report)

class openresa_booking_report(report_sxw.rml_parse):
    
    def __init__(self, cr, uid, name, context):
        super(openresa_booking_report, self).__init__(cr, uid, name, context)
        self.localcontext.update({
            'time': time,
            'datetime':datetime,
        })

report_sxw.report_sxw('report.openresa.booking.report', 'hotel.reservation',
      'addons/openresa/report/openresa_booking_report.rml', parser=openresa_booking_report)

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
