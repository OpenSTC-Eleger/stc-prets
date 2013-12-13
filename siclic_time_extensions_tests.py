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