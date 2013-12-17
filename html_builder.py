from string import Template


def format_resource_plannings(plannings):
    for planning in plannings.get('weeks'):
        output = ['<html>', '<head>', '</head>', '<body>']
        planning['bookable_name'] = plannings.get('bookable_name')
        output.append(format_resource_planning(planning))
        output.append('</body></html>')
    return ''.join(output)


def format_resource_planning(planning):
    output = [planning_template_header.substitute(planning), '<table><tbody>']
    for week_day in planning.get('bookings'):
        output.append(planning_day_row.substitute(day=week_day[0]))
        for booking in week_day[1]:
            booking['resources'] = ''.join(map(lambda r: planning_resource_string.substitute(r), booking.get('resources')))
            output.append(format_event_line(booking))
    output.append('</tbody></table>')
    return ''.join(output)


def format_event_line(event):
    return planning_event_row.substitute(event)


def format_resource_string(resource):
    return planning_resource_string.substitute(resource)


planning_template_header = Template("""
<h1>$bookable_name  <small>$first_day / $last_day</small></h1>
""")

planning_day_row = Template("""
<tr><td colspan="6">$day</td></tr>
""")

planning_event_row = Template("""
<tr>
<td>$start_hour - $end_hour</td>
<td>$name</td>
<td>$booker_name</td>
<td>$contact_name</td>
<td><ul>$resources</ul></td>
<td>$note</td>
</tr>
""")

planning_resource_string = Template("""
<li>$quantity x $name</li>
""")
