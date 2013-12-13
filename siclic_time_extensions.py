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
