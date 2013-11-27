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

import types

from osv import fields, osv
from datetime import datetime, timedelta
import calendar
from dateutil import rrule
from dateutil import parser
from dateutil import relativedelta
import netsvc
import pytz
from tools.translate import _

class openresa_reservation_recurrence(osv.osv):
    _inherit = 'openresa.reservation.recurrence'
    WEIGHT_SELECTION = [('first','First'),('second','Second'),('third','Third'),('fourth','Fourth'),('last','Last')]
    DAY_SELECTION = [('monday','Monday'),('tuesday','Tuesday'),('wednesday','Wednesday'),('thursday','Thursday'),('friday','Friday'),('saturday','Saturday'),('sunday','Sunday')]
    TYPE_RECUR = [('daily','Daily'),('weekly','Weekly'),('monthly','Monthly')]

    #TODO : define state on recurrence
    def return_state_values(self, cr, uid, context=None):
        return [('draft', 'Saisie des infos personnelles'),('confirm','Réservation confirmée'),('cancle','Annulée'),('in_use','Réservation planifiée'),('done','Réservation Terminée'), ('remplir','Saisie de la réservation'),('wait_confirm','En Attente de Confirmation')]

    def _get_state_values(self, cr, uid, context=None):
        return self.return_state_values(cr, uid, context)

    _actions = {
        'confirm': True ,
        'cancel': True,
        'done': True,
    }

    def _get_actions(self, cr, uid, ids, myFields ,arg, context=None):
        #default value: empty string for each id
        ret = {}.fromkeys(ids,'')
        groups_code = []
        groups_code = [group.code for group in self.pool.get("res.users").browse(cr, uid, uid, context=context).groups_id if group.code]

        #evaluation of each _actions item, if test returns True, adds key to actions possible for this record
        for record in self.browse(cr, uid, ids, context=context):
            #ret.update({inter['id']:','.join([key for key,func in self._actions.items() if func(self,cr,uid,inter)])})
            ret.update({record.id:[key for key,func in self._actions.items() if func(self,cr,uid,record,groups_code)]})

    _columns = {
        'reservation_ids':fields.one2many('hotel.reservation','recurrence_id','Generated reservations'),
        'recur_periodicity':fields.integer('Periodicity'),
        'recur_week_monday':fields.boolean('Mon'),
        'recur_week_tuesday':fields.boolean('Tue'),
        'recur_week_wednesday':fields.boolean('Wed'),
        'recur_week_thursday':fields.boolean('Thu'),
        'recur_week_friday':fields.boolean('Fri'),
        'recur_week_saturday':fields.boolean('Sat'),
        'recur_week_sunday':fields.boolean('Sun'),
        'recur_month_absolute':fields.integer('Mounth day'),
        'recur_month_relative_weight':fields.selection(WEIGHT_SELECTION, 'Weight Month'),
        'recur_month_relative_day':fields.selection(DAY_SELECTION, 'Day month'),
        'recur_type':fields.selection(TYPE_RECUR,'Type'),
        'date_start':fields.related('template_id','checkin', type="datetime", string='First occurrence date'),
        'date_end':fields.datetime('Last occurrence to generate', required=False),
        'recur_occurrence_nb':fields.integer('Nb of occurrences'),
        'date_confirm':fields.date('Date of confirm'),
        'recurrence_state': fields.selection(_get_state_values, 'Etat',readonly=True),
        'actions':fields.function(_get_actions, method=True, string="Actions possibles",type="char", store=False),
        }


    _defaults = {
        'recur_periodicity':lambda *a: 1,
        'recur_type':lambda *a: 'daily',
        'recur_occurrence_nb':lambda *a: 1,
        'is_template': lambda *a: True,
        }

    """
    @param id: id or recurrence to generate dates
    @return: list of tuple of checkin,checkout in standard format [('YYYY-mm-yy HH:MM:SS','YYYY-mm-yy HH:MM:SS')] in UTC
    @note: This method is used internally in OpenERP StandAlone, but could be used in xmlrpc call for custom UI
    => daily recurrence: repeat same resa each x days from date_start to date_end
    => weekly recurrence: repeat same resa for xxx,xxx,xxx weekdays each x weeks from date_start to date_end
    => monthly recurrence 1: repeat same resa each absolute day (the 3rd of each month) of a month each x months from date_start to date_end
    => monthly recurrence 2: repeat same resa each relative day (third Friday of each month)of a month each x months from date_start to date_end
    """
    def get_dates_from_setting(self, cr, uid, id, context=None):
        recurrence = self.browse(cr, uid, id, context=context)
        dates = []
        periodicity = recurrence.recur_periodicity
        date_start = fields.datetime.context_timestamp(cr, uid, datetime.strptime(recurrence.date_start, '%Y-%m-%d %H:%M:%S'),context=context)
        date_end = fields.datetime.context_timestamp(cr, uid, datetime.strptime(recurrence.date_end, '%Y-%m-%d %H:%M:%S'),context=context) if recurrence.date_end else False

        switch_date = {
            'monday':relativedelta.MO,
            'tuesday':relativedelta.TU,
            'wednesday':relativedelta.WE,
            'thursday':relativedelta.TH,
            'friday':relativedelta.FR,
            'saturday':relativedelta.SA,
            'sunday':relativedelta.SU
        }
        if not periodicity:
            periodicity = 1
        if recurrence.recur_type == 'daily':
            dates = rrule.rrule(rrule.DAILY, interval=periodicity, dtstart=date_start, until=date_end)
            #if date_end <> last_occurence, we add it to dates generated (means date_end > last_occurence)
        elif recurrence.recur_type == 'weekly':
            #get weekdays to generate
            weekdays = [val for key,val in switch_date.items() if recurrence['recur_week_'+key]]
            dates = rrule.rrule(rrule.WEEKLY, byweekday=weekdays, interval=periodicity, dtstart=date_start, until=date_end)
            #if date_end <> last_occurence, we add it to dates generated (means date_end > last_occurence)
        elif recurrence.recur_type == 'monthly':
            #get nb of occurences to generate
            count = recurrence.recur_occurrence_nb
            if not count:
                count = 1
            switch = {
                'first':1,
                'second':2,
                'third':3,
                'fourth':4,
                'last':-1
                }
            if recurrence.recur_month_relative_day and recurrence.recur_month_relative_weight:
                dates = rrule.rrule(rrule.MONTHLY, interval=periodicity, dtstart=date_start, count=count,
                                    byweekday=switch_date[recurrence.recur_month_relative_day](switch[recurrence.recur_month_relative_weight]))

            elif recurrence.recur_month_absolute:
                dates = rrule.rrule(rrule.MONTHLY, bymonthday=recurrence.recur_month_absolute, interval=periodicity, dtstart=date_start, count=count)
            else:
                raise osv.except_osv(_('Error'),_('You must provide a complete setting for once of monthly recurrence method'))
        else:
            raise osv.except_osv(_('Error'), _('You must set an existing type of recurrence'))
        ret = list(dates)
        #remove date_start values from list if generated too by recurrence
        if ret[0] == date_start:
            ret.pop(0)
        return ret


    """
    @param id: id of recurrence to put dates
    @param dates: list of str_dates of resa to create
    @note: this is the method used to handle common xmlrpc call, it will parse standard date to DateTime date
    and call main method 'generate_reservations'
    """
    def populate_reservations(self, cr, uid, id, dates, context=None):
        if not context:
            context = self.pool.get('res.users').context_get(cr, uid, context=context)
        dates_check = [datetime.strptime(val, '%Y-%m-%d %H:%M:%S') for val in dates]
        return self.generate_reservations(cr, uid, [id], dates=dates_check, context=context)

    """
    @param ids: ids of recurrence to generate dates
    @param dates: dates of resa to generate for recurrence ids
    @note: Generate dates according to recurrence setting. Replace current values on one2many by new ones
    can be used in OpenERP StandAlone or in xmlrpc call as well
    in SWIF context, use dates parameter and ids (even if there is only one recurrence on the list ids)
    I put dates parameter after context to be fully usable both in 'OpenERP button call' or in 'xmlrpc call'
    """
    def generate_reservations(self, cr, uid, ids, context=None, dates=False):
        if not isinstance(ids, list):
            ids = [ids]
        resa_obj = self.pool.get('hotel.reservation')
        for recurrence in self.read(cr, uid, ids, ['template_id','reservation_ids','date_start'], context=context):
            #get template to be used to generate occurrences
            template_id = recurrence['template_id']
            if template_id:
                template = resa_obj.read(cr, uid, template_id[0], ['checkin','checkout'], context=context)
                #remove values of one2many reservation_ids (need to unlink to remove resa)
                if recurrence['reservation_ids']:
                    to_remove_ids = recurrence['reservation_ids']
                    to_remove_ids.remove(template['id'])
                    if to_remove_ids:
                        resa_obj.unlink(cr, uid, to_remove_ids, context=context)
                #then, add template to one2many reservation_ids
                resa_obj.write(cr, uid, template['id'],{'recurrence_id':recurrence['id']})
                #retrieve dates according to recurrence setting or according to parameter
                dates_check = dates and dates or self.get_dates_from_setting(cr, uid, recurrence['id'], context=context)

                #retrieve duration of template resa
                template_checkin = fields.datetime.context_timestamp(cr, uid, datetime.strptime(template['checkin'], '%Y-%m-%d %H:%M:%S'), context=context)
                template_checkout = fields.datetime.context_timestamp(cr, uid, datetime.strptime(template['checkout'], '%Y-%m-%d %H:%M:%S'), context=context)
                #get only timedelta.days value to retrieve checkout of each occurrences
                duration_days = timedelta(template_checkout.day - template_checkin.day)

                #for each date, copy new reservation from template_id (which will populate one2many reservation_ids)
                utc_timezone = pytz.timezone('UTC')
                local_timezone = pytz.timezone(context.get('tz'))
                for item in dates_check:
                    #compute all checkin-checkout converting dates from local_tz to UTC
                    checkin = item.replace(tzinfo=None)
                    checkout = (checkin + duration_days).replace(hour=template_checkout.hour, minute=template_checkout.minute,tzinfo=None)
                    checkin = str(local_timezone.localize(checkin).astimezone(utc_timezone))
                    checkout = str(local_timezone.localize(checkout).astimezone(utc_timezone))
                    resa = resa_obj.copy(cr, uid, template['id'],{'checkin':checkin,
                                                                  'checkout':checkout,
                                                                  'recurrence_id':recurrence['id'],
                                                                  'is_template':False},context=context)
            else:
                raise osv.except_osv(_('Error'),_('You have to specify a template to generate occurrences of this recurrence'))
        return True

    """
    @param ids: recurrence to validate
    @note: validate all VALIDABLE occurrences of the recurrence
    an occurrence can be validated when all product(s) are 'dispo'
    """
    def validate(self, cr, uid, ids, state, context=None):
        wkf_service = netsvc.LocalService('workflow')
        now = datetime.now().strftime('%Y-%m-%d')
        for recurrence in self.browse(cr, uid, ids, context=context):
            #count to know how many resa have been requested to be confirmed,
            #recurrence is updated to confirmed only if one or more recurrence has been requested to be confirmed
            resa_count = 0
            for resa in recurrence.reservation_ids:
                if resa.all_dispo and resa.state in ['remplir','draft']:
                    resa_count += 1
                    wkf_service.trg_validate(uid, 'hotel.reservation', resa.id, state, cr)
            if resa_count > 0:
                recurrence.write({'date_confirm':now})
        return True

    def write(self, cr, uid, ids, vals, context=None):
        isList = isinstance(ids, types.ListType)
        if isList == False :
            ids = [ids]

        if vals.has_key('state') :
            self.validate(cr, uid, ids, vals['state'], context)

        res = super(openresa_reservation_recurrence, self).write(cr, uid, ids, vals, context=context)
        return res

openresa_reservation_recurrence()