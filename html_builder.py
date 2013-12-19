from string import Template
from datetime import datetime
from siclic_time_extensions import week_days_list

def format_resource_plannings(plannings):
    output = ['<html>', '<head>',
              "<link href='http://netdna.bootstrapcdn.com/bootstrap/3.0.3/css/bootstrap.min.css' rel='stylesheet'>",
              "<style type='text/css'>.pagebreak { page-break-after: always; } td { font-size: 80%; } h1 { font-size: 180%; }</style>",
              '</head>', '<body>']
    for planning in plannings.get('weeks'):
        planning['bookable_name'] = plannings.get('bookable_name')
        output.append(format_resource_planning(planning))
        output.append("<hr class='pagebreak'/>")

    output.append('</body></html>')
    return ''.join(output)


def format_resource_planning(planning):
    planning['first_day'] = datetime.strftime(datetime.strptime(planning.get('first_day'), '%Y-%m-%d %H:%M:%S'), '%d-%m-%Y')
    planning['last_day'] = datetime.strftime(datetime.strptime(planning.get('last_day'), '%Y-%m-%d %H:%M:%S'), '%d-%m-%Y')
    output = [planning_template_header.substitute(planning), "<table class='table table-condensed'><tbody>"]
    for week_day in planning.get('bookings'):
        day_of_week_cell = ' '.join([week_days_list[week_day[0].weekday()], datetime.strftime(week_day[0], '%d-%m-%Y')])
        output.append(planning_day_row.substitute(day=day_of_week_cell))
        for booking in week_day[1]:
            resources = booking.get('resources')
            templated_resources = map(lambda r: planning_resource_string.substitute(r), resources)
            booking['templated_resources'] = ''.join(templated_resources)
            output.append(format_event_line(booking))
    output.append('</tbody></table>')
    return ''.join(output)


def format_event_line(event):
    event['formated_start_hour'] = datetime.strftime(event.get('start_hour'), "%H:%M")
    event['formated_end_hour'] = datetime.strftime(event.get('end_hour'), "%H:%M")
    event['formated_note'] = event.get('note') if event.get('note') else ''
    return planning_event_row.substitute(event)


def format_resource_string(resource):
    return planning_resource_string.substitute(resource)


planning_template_header = Template("<h1>$bookable_name  <small>$first_day / $last_day</small></h1>")

planning_day_row = Template("<tr><td colspan='6' class='active'><h4>$day</h4></td></tr>")

planning_event_row = Template("<tr><td>$formated_start_hour - $formated_end_hour</td><td>$name</td><td>$booker_name</td><td>$contact_name</td><td><ul>$templated_resources</ul></td><td>$formated_note</td></tr>")

planning_resource_string = Template("<li>$quantity x $name</li>")
