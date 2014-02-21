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

from datetime import datetime
import unittest
import siclic_time_extensions


class TestWeeksBetweenFunction(unittest.TestCase):

    def setUp(self):
        self.first_date = datetime.strptime('2013-12-01', '%Y-%m-%d')
        self.last_date = datetime.strptime('2013-12-31', '%Y-%m-%d')
        self.expected_weeks_count = 6

    def test_weeks_count(self):
        count = len(siclic_time_extensions.weeks_between(self.first_date, self.last_date))
        self.assertEqual(count, self.expected_weeks_count)

if __name__ == '__main__':
    unittest.main()