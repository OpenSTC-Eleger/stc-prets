import unittest
import html_builder
import datetime


class TestTemplateBuildFunction(unittest.TestCase):
    def setUp(self):
        self.planning_data_sample = [{"bookable_name": "Salle Aristide Briand",
                                      "weeks":
                                          [{"bookings": [
                                              [datetime(2013, 11, 25, 0, 0, 0),
                                               [{"start_hour": datetime(2013, 11, 25, 19, 0, 0),
                                                 "name": "Cours de gymnastique",
                                                 "booker_name": "GYM TONIC",
                                                 "end_hour": datetime(2013, 11, 25, 20, 0, 0),
                                                 "note": false,
                                                 "contact_name":
                                                     " THIEVIN  Fabrice, La Montagne, 24 rue de la république",
                                                 "resources": [{"name": "Salle Aristide Briand", "quantity": 1.0}]},
                                                {"start_hour": datetime(2013, 25, 11, 9, 30, 0)
                                                    ,
                                                 "name": "Ménage ",
                                                 "booker_name": "Technique",
                                                 "end_hour": datetime(2013, 11, 25, 10, 30)
                                                    ,
                                                 "note": false,
                                                 "contact_name": "MALAISÉ  Jannick",
                                                 "resources": [{"name": "Salle Aristide Briand", "quantity": 1.0}]},
                                                {"start_hour": datetime(2013, 25, 11, 20, 15, 0)
                                                    ,
                                                 "name": "Section Chant répétition",
                                                 "booker_name": "A.L.M",
                                                 "end_hour": datetime(2013, 11, 25, 21, 30, 0)
                                                    ,
                                                 "note": false,
                                                 "contact_name":
                                                     " MARTIN  Jacques, La Montagne, Foyer Laïc - 45, rue Violin",
                                                 "resources": [{"name": "Salle Aristide Briand", "quantity": 1.0}]}]
                                              ]]}]
                                     }]

    def test_output_sample(self):
        document = html_builder.format_resource_plannings(self.planning_data_sample)
        print(document)
        self.assertEqual(document, True)


if __name__ == '__main__':
    unittest.main()