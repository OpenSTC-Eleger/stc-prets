from string import Template


def format_plannings(plannings):
    for planning in plannings:
        format_planning(planning)
    return

def format_planning(planning):


planning_template_header = Template("""
<h1>$bookable_name  <small>$start_date / $end_date</small></h1>
""")

planning_template_day =