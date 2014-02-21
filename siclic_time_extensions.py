# -*- coding: utf-8 -*-

##############################################################################
#
#    OpenResa module for OpenERP, module OpenResa
#    Copyright (C) 2012 SICLIC http://siclic.fr
#
#    This file is a part of OpenResa
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

import datetime



def weeks_between(first_date, last_date):
    """
    Returns list of date tuples representing weeks bounds [(first_day_of_week,last_day_of_week),...]

    :first_date; datetime
    :last_date: datetime
    :return: List[Tuple]
    """

    find_first_day_of_week = lambda day: day - (datetime.timedelta(days=day.weekday()))
    find_last_day_of_week = lambda first_day: first_day + (datetime.timedelta(days=6))
    first_day_of_week = find_first_day_of_week(first_date)
    week_list = list()
    while first_day_of_week < last_date:
        week_list.append((first_day_of_week, find_last_day_of_week(first_day_of_week)))
        first_day_of_week = first_day_of_week + datetime.timedelta(days=7)
    return week_list


def days_between(first_date, last_date):
    days = list()
    for delta in range((last_date - first_date).days + 1):
        days.append(first_date + datetime.timedelta(days=delta))
    return days


week_days_list = ('Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche')