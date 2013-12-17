from string import Template


def format_plannings(plannings):
    for planning in plannings[1]:
        format_planning(planning)
    return

def format_planning(planning):
    return

planning_template_header = Template("""
<h1>$bookable_name  <small>$first_day / $last_day</small></h1>
""")

planning_event_row = Template("""
<p></p>
""")