# Importing flask module in the project is mandatory
# An object of Flask class is our WSGI application.
import html
import sys
import time
from datetime import datetime
import json
import os
from urllib.parse import parse_qs, urlparse

import backoff as backoff
import pytz
import re

import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify, Response

# Flask constructor takes the name of
# current module (__name__) as argument.
app = Flask(__name__)


# The route() function of the Flask class is a decorator,
# which tells the application which URL should call
# the associated function.
@app.route('/', methods=['GET', 'POST'])
def start():
    results = {}
    if request.method == 'POST':

        user_input = request.form['user_input']

        if '?' in user_input:
            path, query_string = user_input.split('?', 1)
        else:
            path = user_input
            query_string = ""

        query_params = parse_qs(query_string)
        print(f"\nPath: {path}")
        print(f"Query Parameters: {query_params}\n")

        if path.startswith('/questions/'):
            if path.endswith('/answers'):
                temp = path.split('/')[2]
                id = temp.split(";")
                id = list(dict.fromkeys(id))  # Removes duplicates while preserving order
                results = scrape_answers(id, query_params)
            else:
                temp = path.split('/questions/')[1]
                temp_temp = temp.split('?')[0]
                id = temp_temp.split(";")
                id = list(dict.fromkeys(id))  # Removes duplicates while preserving order
                results = scrape_question_id(id, query_params)
        elif path.startswith('/questions'):
            results = scrape_questions(query_params)
        elif path.startswith('/collectives'):
            results = scrape_collectives(query_params)
        elif path.startswith('/answers/'):
            temp = path.split('/answers/')[1]
            temp_temp = temp.split('?')[0]
            id = temp_temp.split(";")
            id = list(dict.fromkeys(id))  # Removes duplicates while preserving order
            results = scrape_answers_id(id, query_params)

    results_json = json.dumps(results, indent=2)
    print(results_json)
    return render_template('base.html', results=jsonify(results_json))


@app.route('/collectives', methods=['GET', 'POST'])
def api_collectives():
    params = {key: [value] for key, value in request.args.to_dict().items()}
    out = scrape_collectives(params)
    json_out = json.dumps(out, indent=2)
    print(json_out)
    return Response(json_out, content_type='application/json')


def scrape_collectives(params):
    site = params.get("site")
    if not site or site[0] != "stackoverflow":
        return {"error": "The 'site' parameter is required."}

    # check built in filters
    filter = params.get("filter")
    if filter:
        if filter[0] == "none":
            # print(json.dumps("{}", indent=2))
            return {}
        elif filter[0] == "total":
            base_url = 'https://stackoverflow.com/collectives-all'
            soup = test_request(base_url)
            all_collectives = soup.find_all('div', class_='flex--item s-card bs-sm mb12 py16 fc-black-500')
            out = {"total": len(all_collectives)}
            # print(out)
            return out

    base_url = 'https://stackoverflow.com/collectives-all'
    soup = test_request(base_url)
    all_collectives = soup.find_all('div', class_='flex--item s-card bs-sm mb12 py16 fc-black-500')

    # Initialize data structure
    data = {
        "items": [],
        "has_more": False
    }

    for collective in all_collectives:
        collective_href_tag = collective.find('a', class_='js-gps-track')
        collective_href = collective_href_tag['href']
        tags_list, external_link_list, description, collective_href = get_Collective_data(collective_href)
        name = collective_href_tag.get_text()

        # Append to the items list
        data['items'].append({
            "tags": tags_list,
            "external_links": external_link_list,
            "description": description,
            "link": collective_href,
            "name": name,
            "slug": collective_href.split("/")[-1]
        })

    # Print or return the JSON structure
    # print(json.dumps(data, indent=2))
    return data


def get_Collective_data(collective_href):
    collective_url = 'https://stackoverflow.com' + collective_href
    tags_url = collective_url + "?tab=tags&page="
    num = 1
    tags_list = []

    # get tags
    while True:
        cur = tags_url + str(num)
        num = num + 1
        # print(cur)

        tag_soup = test_request(cur)
        tag_tag = tag_soup.find_all('div', class_='grid--item s-card js-tag-cell d-flex fd-column')
        if not tag_tag:
            break
        for cur_tag in tag_tag:
            tag = cur_tag.find('a', class_='s-tag post-tag').get_text()
            # print(tag)
            tags_list.append(tag)

    # get external links
    collective_soup = test_request(collective_url)
    external_link_list = []
    links_group = collective_soup.find('optgroup', label='External links')
    links_tag = links_group.find_all('option')
    for link in links_tag:
        if link.get_text() == "Contact":
            type_ex = "support"
        else:
            type_ex = link.get_text().lower()
        external_link_list.append({
            "type": type_ex,
            "link": link['data-url']
        })

    description_tag = collective_soup.find('div', class_='fs-body1 fc-black-500 d:fc-black-600 mb6 wmx7')
    description = description_tag.get_text()

    return tags_list, external_link_list, description, collective_href


@app.route('/questions', methods=['GET', 'POST'])
def api_question():
    params = {key: [value] for key, value in request.args.to_dict().items()}
    out = scrape_questions(params)
    json_out = json.dumps(out, indent=2)
    print(json_out)
    return Response(json_out, content_type='application/json')


def scrape_questions(params):
    site = params.get("site")
    if not site or site[0] != "stackoverflow":
        return {"error": "The 'site' parameter is required."}

    sort = params.get("sort")

    # base_url = 'https://stackoverflow.com/questions'
    base_url = url_params(params)

    # check built in filters
    filter = params.get("filter")
    withbody = False
    if filter:
        if filter[0] == "none":
            # print(json.dumps("{}", indent=2))
            return {}
        elif filter[0] == "withbody":
            withbody = True

    # Initialize data structure
    question_data = {
        "items": [],
        "has_more": False
    }

    num = 1
    while True:
        soup = test_request(base_url + "&page=" + str(num))
        num = num + 1
        question_summaries = soup.find_all('div', class_='s-post-summary')


        if not question_summaries:
            break

        for x in question_summaries:
            # Find the link within the question summary
            post_id = x.get('data-post-id')
            print(post_id)
            question_data["items"].append(get_question_id_data(post_id, withbody))

        if sort:
            if sort[0] == "hot" or sort[0] == 'week' or sort[0] == 'month':
                break

    filtered_question_data = sort_data(question_data, params)

    if filter:
        if filter[0] == "total":
            out = {"total": len(filtered_question_data["items"])}
            return out

    return filtered_question_data


@app.route('/questions/<ids>', methods=['GET', 'POST'])
def api_question_id(ids):
    params = {key: [value] for key, value in request.args.to_dict().items()}
    id = ids.split(";")
    ids = list(dict.fromkeys(id))  # Removes duplicates while preserving order
    out = scrape_question_id(ids, params)
    json_out = json.dumps(out, indent=2)
    print(json_out)
    return Response(json_out, content_type='application/json')


def scrape_question_id(ids, params):
    site = params.get("site")
    if not site or site[0] != "stackoverflow":
        return {"error": "The 'site' parameter is required."}

    # check built in filters
    withbody = False
    filter = params.get("filter")
    if filter:
        if filter[0] == "none":
            # print(json.dumps("{}", indent=2))
            return {}
        elif filter[0] == "withbody":
            withbody = True

    # Initialize data structure
    question_data = {
        "items": [],
        "has_more": False
    }
    for id in ids:
        question_data["items"].append(get_question_id_data(id, withbody))

    filtered_question_data = sort_data(question_data, params)

    if filter:
        if filter[0] == "total":
            out = {"total": len(filtered_question_data["items"])}
            return out

    # Print or return the JSON structure
    # print(json.dumps(filtered_question_data, indent=2))
    return filtered_question_data


def get_question_id_data(id, withbody):
    base_url = 'https://stackoverflow.com/questions'
    post_url = base_url + "/" + id + "?noredirect=anything"
    post_soup = test_request(post_url)

    # Extract tags
    tag_list = post_soup.find('div', class_='post-taglist')
    if tag_list:
        tags = [tag.get_text(strip=True) for tag in tag_list.find_all('a', class_='post-tag')]
    else:
        # print(json.dumps(question_data, indent=2))
        return

    # Extract owner information
    num = 0
    loop = True
    while loop:
        num = num + 1
        revision_soup = test_request("https://stackoverflow.com/posts/" + str(id) + "/revisions?page=" + str(num))
        revision_tags = revision_soup.find_all("div", class_="mb12 js-revision")
        for rev_element in revision_tags:
            tag_num = rev_element.find("div", title="revision 1")
            if tag_num:
                user_tag = rev_element.find("div", class_="s-user-card--info")
                user_href_tag = user_tag.find("a", href=True)
                if user_href_tag:
                    user_href = user_href_tag["href"]
                loop = False
                break
            else:
                continue

    if user_href_tag:
        user_soup = test_request("https://stackoverflow.com" + str(user_href))

        owner_link = "https://stackoverflow.com" + user_href
        user_id = user_href.split('/')[2]

        profile_container = user_soup.find("div", class_="bar-md bs-sm")
        profile_tag = profile_container.find("img", src=True)
        profile_image = profile_tag["src"]

        owner_sig = post_soup.find('div', class_='post-signature owner flex--item')
        is_community_owned = False
        if owner_sig:
            reputation_tag = owner_sig.find('span', class_='reputation-score')
            reputation = reputation_tag['title'].split(' ')[2].replace(',', '')
            if (reputation == ""):
                reputation = reputation_tag.get_text(strip=True).replace(',', '')
            user_tag = owner_sig.find('div', class_='user-details')
            display_name_clean = user_tag.find('a').text
            display_name = display_name_clean

        else:  # community owned
            display_name_tag = user_soup.find('div', class_="flex--item mb12 fs-headline2 lh-xs")
            display_name = display_name_tag.get_text(strip=True)
            reputation_tag = user_soup.find("div", class_="fs-body3 fc-black-600")
            reputation = reputation_tag.get_text(strip=True).replace(",", "")
            community_owned_date = get_revision_question(id, 'community')
            is_community_owned = True

        if (user_soup.find("div", class_="flex--item s-badge s-badge__moderator")):
            user_type = 'moderator'
        else:
            user_type = 'registered'

        # Get account ID
        script_tag = user_soup.find('script', string=lambda s: s and 'StackExchange.user.init' in s)
        script_content = script_tag.string
        start_index = script_content.find('accountId:') + len('accountId:')
        end_index = script_content.find('}', start_index)
        account_id = script_content[start_index:end_index].strip()

    else:  # deleted user
        user_type = "does_not_exist"
        display_name = user_tag.get_text(strip=True)
        owner_sig = post_soup.find('div', class_='post-signature owner flex--item')
        is_community_owned = False
        if not owner_sig:
            community_owned_date = get_revision_question(id, 'community')
            is_community_owned = True

    # Extract other information
    answer_tag = post_soup.find('div', id='answers-header')
    answer_count_tag = answer_tag.find('h2', {'data-answercount': True})
    answer_count = answer_count_tag['data-answercount']

    answered_tag = post_soup.find('div', {'data-answerid': True})
    is_answered = False
    accepted_answer = False
    if answered_tag:
        answer_score = int(answered_tag["data-score"])
        if answer_score > 0:
            is_answered = True
        if " ".join(answered_tag['class']) == 'answer js-answer accepted-answer js-accepted-answer':
            is_answered = True

    answered_tag = post_soup.findAll('div', {'data-answerid': True})
    if answered_tag:
        for answer in answered_tag:
            if " ".join(answer['class']) == 'answer js-answer accepted-answer js-accepted-answer':
                accepted_answer = True
                accepted_answer_id = answer['data-answerid']
                break

    view_count_tag = post_soup.find('div', class_='flex--item ws-nowrap mb8')
    if not view_count_tag:
        view_count_tag = post_soup.find('div', class_='flex--item ws-nowrap mb8 mr16')
    view_count_title = view_count_tag.get('title', '')
    view_count = view_count_title.split()[1].replace(',', '')

    score_tag = post_soup.find('div', class_='js-vote-count')
    score = score_tag.get_text(strip=True)

    last_activity_tag = post_soup.find('a', href='?lastactivity')
    last_activity_date = convert_to_epoch(last_activity_tag['title'])

    creation_date_tag = post_soup.find('time', itemprop='dateCreated')
    creation_date = convert_to_epoch(creation_date_tag['datetime'])

    link_tag = post_soup.find('link', rel='canonical')
    link = link_tag['href']

    title_tag = post_soup.find('div', id='question-header')
    title_clean = title_tag.find('h1', class_='fs-headline1 ow-break-word mb8 flex--item fl1').text.strip()
    title = title_clean

    question_post_tag = post_soup.find('div', class_='post-layout')
    is_edited = question_post_tag.find('div', class_='post-signature flex--item')
    if (is_edited):
        last_edit_date_tag = is_edited.find('span', class_='relativetime')
        last_edit_date = convert_to_epoch(last_edit_date_tag['title'])

    is_closed = False
    is_locked = False
    is_bounty = False
    closed_reason = 'na'
    notice_tag = post_soup.select('aside.s-notice.s-notice__info.post-notice.js-post-notice.mb16')
    for notice in notice_tag:
        is_closed_tag = notice.find_all(string='Closed ')
        for tag in is_closed_tag:
            parent_div = tag.find_parent('div')
            date_span = parent_div.find('span', title=True)
            if date_span:
                is_closed = True
                if title.endswith('[closed]') or title.endswith('[duplicate]'):
                    title = title.replace(' [closed]', '')
                    title = title.replace(' [duplicate]', '')
                closed_date = convert_to_epoch(date_span.get('title'))
                revision_soup = test_request("https://stackoverflow.com/posts/" + id + "/revisions")
                revisions_tag = revision_soup.find_all("div", class_='mb12 js-revision')

                done = False
                for tag in revisions_tag:
                    if (done == True):
                        break
                    b_tag = tag.find_all('b')
                    for temp in b_tag:
                        if "Post Closed" in tag.text:
                            closed_tag = temp.find_parent('div')
                            closed_reason = closed_tag.get_text(strip=True).split('"')[1]
                            done = True
                            break

        is_bounty_tag = notice.find_all(string='bounty')
        for tag in is_bounty_tag:
            parent_div = tag.find_parent('div')
            date_span = parent_div.find('span', title=True)
            if date_span:
                is_bounty = True
                bounty_closes_date = convert_to_epoch(date_span.get('title'))
                bounty_amount_tag = parent_div.find('span',
                                                    class_='s-badge s-badge__bounty d-inline px4 py2 ba bc-transparent bar-sm fs-caption va-middle')
                bounty_amount = bounty_amount_tag.get_text()[1:]
                break

        is_locked_tag = notice.find_all('svg', class_='svg-icon iconLock')
        if is_locked_tag:
            is_locked = True
            locked_date = get_revision_question(id, 'locked')

    protected_date = get_revision_question(id, 'protected')

    if withbody:
        post_body_tag = post_soup.find('div', class_="s-prose js-post-body")
        body_tag = post_body_tag.find_all(recursive=False)
        body = "".join([str(p) + "\n" for p in body_tag if p.name != 'div'])
        body = convert_body_to_html_entities(body)

    # check migrated
    migrated = get_migrated_data(id)

    # Add extracted data to the JSON structure
    items = ({
        "tags": tags,
        **({"migrated_from": migrated} if migrated else {}),
        "owner": {
            **({"account_id": int(account_id)} if user_href_tag else {}),
            **({"reputation": int(reputation)} if user_href_tag and reputation else {}),
            **({"user_id": int(user_id)} if user_href_tag else {}),
            "user_type": user_type,
            **({"profile_image": profile_image} if user_href_tag and profile_image else {}),
            "display_name": convert_to_html_entities(display_name),
            **({"link": owner_link} if user_href_tag else {})
        },
        "is_answered": is_answered,
        "view_count": int(view_count),
        **({"closed_date": closed_date} if is_closed else {}),
        **({"bounty_amount": int(bounty_amount)} if is_bounty else {}),
        **({"bounty_closes_date": bounty_closes_date} if is_bounty else {}),
        **({"protected_date": protected_date} if protected_date else {}),
        **({"accepted_answer_id": int(accepted_answer_id)} if accepted_answer else {}),
        "answer_count": int(answer_count),
        **({"community_owned_date": community_owned_date} if is_community_owned else {}),
        "score": int(score),
        **({"locked_date": locked_date} if is_locked else {}),
        "last_activity_date": last_activity_date,
        "creation_date": creation_date,
        **({"last_edit_date": last_edit_date} if is_edited else {}),
        "question_id": int(id),
        "link": link,
        **({"closed_reason": closed_reason} if is_closed else {}),
        "title": convert_to_html_entities(title),
        **({"body": body} if withbody else {})
    })

    return items


def convert_to_epoch(date_string):
    # Define the date format
    date_formats = [
        "%Y-%m-%dT%H:%M:%S",  # Format without timezone
        "%Y-%m-%d %H:%M:%S%z",  # Format with 'Z' replaced by '+0000'
    ]

    for date_format in date_formats:
        try:
            # Handle 'Z' by replacing it with '+0000' to indicate UTC time explicitly
            if 'Z' in date_string:
                date_string = date_string.replace('Z', '+0000')

            # Convert the date string to a datetime object
            dt = datetime.strptime(date_string, date_format)

            # Assuming the datetime is in GMT
            dt = dt.replace(tzinfo=pytz.timezone('GMT'))

            # Convert the datetime object to an epoch timestamp
            epoch_timestamp = int(dt.timestamp())

            return epoch_timestamp
        except ValueError:
            # If parsing fails, continue to the next format
            continue


@app.route('/answers/<ids>', methods=['GET', 'POST'])
def api_answers_id(ids):
    params = {key: [value] for key, value in request.args.to_dict().items()}
    id = ids.split(";")
    ids = list(dict.fromkeys(id))  # Removes duplicates while preserving order
    out = scrape_answers_id(ids, params)
    json_out = json.dumps(out, indent=2)
    print(json_out)
    return Response(json_out, content_type='application/json')


def scrape_answers_id(ids, params):
    site = params.get("site")
    if not site or site[0] != "stackoverflow":
        return {"error": "The 'site' parameter is required."}

    # check built in filters
    filter = params.get("filter")
    if filter:
        if filter[0] == "none":
            # print(json.dumps("{}", indent=2))
            return {}

    # Initialize data structure
    answer_data = {
        "items": [],
        "has_more": False
    }

    for id in ids:
        base_url = 'https://stackoverflow.com/a'
        post_url = base_url + "/" + id + "?noredirect=anything"
        post_soup = test_request(post_url)
        answer_data['items'].extend(get_answers_data(id, post_soup, params))

    filtered_answer_data = sort_data(answer_data, params)

    if filter:
        if filter[0] == "total":
            out = {"total": len(filtered_answer_data["items"])}
            return out

    # Print or return the JSON structure
    # print(json.dumps(filtered_answer_data, indent=2))
    return filtered_answer_data


def get_answers_data(id, post_soup, params):
    # check built in filters
    withbody = False
    filter = params.get("filter")
    if filter:
        if filter[0] == "withbody":
            withbody = True

    answers_tag = post_soup.find('div', id='answers')
    if not answers_tag:
        return []
    temp = 'answer-' + str(id)
    answer_tag = answers_tag.find('div', id=temp)

    if not answer_tag:
        return []

    # owners information
    is_edited = False
    comm_owned = False
    other_sig = answer_tag.find_all('div', class_='post-signature flex--item fl0')

    if len(other_sig) > 1:
        sig_tag = other_sig[1]
        answer_date = sig_tag.find('div', class_='user-action-time fl-grow1')
        if answer_date:  # not community owned
            is_edited = True
            date_span = answer_date.find('span')['title']
            creation_date = convert_to_epoch(date_span)
            edit_date = other_sig[0].find('div', class_='user-action-time fl-grow1')
            edit_date_span = edit_date.find('span')['title']
            last_edit_date = convert_to_epoch(edit_date_span)
            ## case where community bot edits so musnt take that time as last activity
            edit_tag = other_sig[0]
            bot_details = edit_tag.find("div", class_="user-details")
            if bot_details:
                if bot_details.get_text(strip=True) == "CommunityBot111 silver badge":
                    last_activity_date = comm_bot_activity_date(id)
                else:
                    last_activity_date = last_edit_date


        else:  # community owned
            comm_owned = True
            user_details_tag = sig_tag.find_all('div', class_='user-details')[1]
            revision_href = user_details_tag.find('a', href=True)['href']
            revision_url = 'https://stackoverflow.com/' + str(revision_href) + "?page="
            num = 0
            not_found = True

            while not_found:
                num = num + 1
                revision_soup = test_request(revision_url + str(num))
                sections = revision_soup.find_all('div', class_="mb12 js-revision")

                for element in sections:
                    if element.get_text(strip=True).__contains__('Post Made Community Wiki'):
                        com_date_tag = element.find('span', title=True)
                        community_owned_date = convert_to_epoch(com_date_tag['title'])
                    if element.find("div", title="revision 1"):
                        not_found = False


            temp_tag = other_sig[0].find('div', class_='user-action-time fl-grow1')
            if temp_tag.get_text(strip=True).__contains__("answered"):
                date_span = temp_tag.find('span')['title']
                creation_date = convert_to_epoch(date_span)
                last_activity_date = creation_date
            else:  # edited
                is_edited = True
                edit_date_span = temp_tag.find('span')['title']
                last_edit_date = convert_to_epoch(edit_date_span)
                last_activity_date = last_edit_date
                created_date_tag = answer_tag.find('time', itemprop='dateCreated')
                creation_date = convert_to_epoch(created_date_tag['datetime'])

    else:
        is_edited = False
        edge_case = answer_tag.find('div', class_="post-signature owner flex--item fl0")
        if edge_case:
            sig_tag = edge_case
            answer_date = sig_tag.find('div', class_='user-action-time fl-grow1')
            if answer_date:  # not community owned
                is_edited = True
                date_span = answer_date.find('span')['title']
                creation_date = convert_to_epoch(date_span)
                edit_date = other_sig[0].find('div', class_='user-action-time fl-grow1')
                edit_date_span = edit_date.find('span')['title']
                last_edit_date = convert_to_epoch(edit_date_span)
                last_activity_date = last_edit_date
                ## case where community bot edits so musnt take that time as last activity
                edit_tag = other_sig[0]
                bot_details = edit_tag.find("div", class_="user-details")
                if bot_details:
                    if bot_details.get_text(strip=True) == "CommunityBot111 silver badge":
                        last_activity_date = comm_bot_activity_date(id)
                    else:
                        last_activity_date = last_edit_date
            else:  # community owned
                comm_owned = True
                user_details_tag = sig_tag.find_all('div', class_='user-details')[1]
                revision_href = user_details_tag.find('a', href=True)['href']
                revision_url = 'https://stackoverflow.com/' + str(revision_href) + "?page="
                num = 0
                not_found = True

                while not_found:
                    num = num + 1
                    revision_soup = test_request(revision_url + str(num))
                    sections = revision_soup.find_all('div', class_="mb12 js-revision")

                    for element in sections:
                        if element.get_text(strip=True).__contains__('Post Made Community Wiki'):
                            com_date_tag = element.find('span', title=True)
                            community_owned_date = convert_to_epoch(com_date_tag['title'])
                        if element.find("div", title="revision 1"):
                            not_found = False

                temp_tag = other_sig[0].find('div', class_='user-action-time fl-grow1')
                if temp_tag.get_text(strip=True).__contains__("answered"):
                    date_span = temp_tag.find('span')['title']
                    creation_date = convert_to_epoch(date_span)
                    last_activity_date = creation_date
                else:  # edited
                    is_edited = True
                    edit_date_span = temp_tag.find('span')['title']
                    last_edit_date = convert_to_epoch(edit_date_span)
                    last_activity_date = last_edit_date
                    created_date_tag = answer_tag.find('time', itemprop='dateCreated')
                    creation_date = convert_to_epoch(created_date_tag['datetime'])
        else:
            sig_tag = other_sig[0]
            answer_date = sig_tag.find('div', class_='user-action-time fl-grow1')
            if answer_date:
                date_span = answer_date.find('span')['title']
                creation_date = convert_to_epoch(date_span)
                last_activity_date = creation_date


    user_ref = None
    user_details_tag = sig_tag.find_all('div', class_='user-details')
    if len(user_details_tag) > 1:
        user_tag = user_details_tag[1]
        num = 0
        loop = True
        while loop:
            num = num + 1
            revision_soup = test_request("https://stackoverflow.com/posts/" + str(id) + "/revisions?page=" + str(num))
            revision_tags = revision_soup.find_all("div", class_="mb12 js-revision")
            for rev_element in revision_tags:
                tag_num = rev_element.find("div", title="revision 1")
                if tag_num:
                    user_tags = rev_element.find("div", class_="s-user-card--info")
                    user_href_tag = user_tags.find("a", href=True)
                    if user_href_tag:
                        user_ref = user_href_tag["href"]
                    loop = False
                    break
                else:
                    continue

    else:
        user_tag = user_details_tag[0]
        a_tag = user_tag.find('a')
        if a_tag:
            user_ref = a_tag['href']

    if user_ref:
        user_id = user_ref.split('/')[2]
        profile_link = "https://stackoverflow.com" + user_ref
        user_soup = test_request(profile_link)
        owner_link_tag = user_soup.find('meta', property='og:url')
        owner_link = owner_link_tag['content']
        display_name_tag = user_soup.find('div', class_="flex--item mb12 fs-headline2 lh-xs")
        display_name_clean = display_name_tag.get_text(strip=True)
        display_name = display_name_clean
        stats_tag = user_soup.find('div', id="stats")
        reputation_tag = stats_tag.find('div', class_='flex--item md:fl-auto')
        reputation = reputation_tag.get_text().replace(',', '').split(' ')[0]
        profile_container = user_soup.find("div", class_="bar-md bs-sm")
        profile_tag = profile_container.find("img", src=True)
        profile_image = profile_tag["src"]

        if (user_soup.find("div", class_="flex--item s-badge s-badge__moderator")):
            user_type = 'moderator'
        else:
            user_type = 'registered'

        script_tag = user_soup.find('script', string=lambda s: s and 'StackExchange.user.init' in s)
        script_content = script_tag.string
        start_index = script_content.find('accountId:') + len('accountId:')
        end_index = script_content.find('}', start_index)
        account_id = script_content[start_index:end_index].strip()

    else: # Deleted
        user_type = "does_not_exist"
        display_name = user_tag.find('span', itemprop="name")
        if display_name:
            display_name.get_text(strip=True)
        else:
            display_name_temp = user_tag.get_text(strip=True).split("%")
            if len(display_name_temp) > 1:
                display_name = display_name_temp[-1]
            else:
                display_name = display_name_temp[0]



    # other information
    is_answered_Class = answer_tag['class']
    class_string = ' '.join(is_answered_Class)
    is_accepted = class_string == 'answer js-answer accepted-answer js-accepted-answer'

    score = answer_tag['data-score']
    question_id = answer_tag['data-parentid']

    # collective recommended
    endorsements_tag = answer_tag.find("div", class_="js-endorsements")
    if endorsements_tag:
        collective_href_tag = endorsements_tag.find('a', href=True)
        if collective_href_tag:

            revision_url = 'https://stackoverflow.com/posts/' + str(id) + "/revisions?page="
            num = 0
            not_found = True

            while not_found:
                num = num + 1
                revision_soup = test_request(revision_url + str(num))
                sections = revision_soup.find_all('div', class_="mb12 js-revision")

                for element in sections:
                    if element.get_text(strip=True).__contains__('Recommended answer'):
                        collective_date_tag = element.find('span', title=True)
                        collective_creation_date = convert_to_epoch(collective_date_tag['title'])
                        not_found = False
                        break
                    if element.find("div", title="revision 1"):
                        not_found = False

            collective_href = collective_href_tag['href']
            tags_list, external_link_list, description, collective_href = get_Collective_data(collective_href)
            name = collective_href_tag.get_text()
            collective = []
            collective.append({
                "collective": {
                    "tags": tags_list,
                    "external_links": external_link_list,
                    "description": description,
                    "link": collective_href,
                    "name": name,
                    "slug": collective_href.split("/")[-1]
                },
                "creation_date": collective_creation_date
            })

    # Collective recognized
    recognized_tag = answer_tag.find("div", class_="s-user-card--type affiliate-badge px8 pb8 mtn4 fs-caption")
    if recognized_tag:
        recognized_href_tag = recognized_tag.find("a", href=True)
        if recognized_href_tag:
            recognized_href = recognized_href_tag["href"]
            tags_list, external_link_list, description, collective_href = get_Collective_data(recognized_href)
            name = recognized_href_tag.get_text(strip=True).replace("Recognized by ", "")
            rec_collective = []
            rec_collective.append({
                "tags": tags_list,
                "external_links": external_link_list,
                "description": description,
                "link": collective_href,
                "name": name,
                "slug": collective_href.split("/")[-1]
            })

    if withbody:
        post_body_tag = answer_tag.find('div', class_="s-prose js-post-body")
        body_tag = post_body_tag.find_all(recursive=False)
        body = "".join([str(p) + "\n" for p in body_tag])
        body = convert_body_to_html_entities(body)

    # Add extracted data to the JSON structure
    answer_data = []
    answer_data.append({
        **({"recommendations": collective} if (endorsements_tag and collective_href_tag) else {}),
        **({"posted_by_collectives": rec_collective} if (recognized_tag and recognized_href_tag) else {}),
        "owner": {
            ** ({"account_id": int(account_id)} if user_ref else {}),
            **({"reputation": int(reputation)} if user_ref and reputation else {}),
            **({"user_id": int(user_id)} if user_ref else {}),
            "user_type": user_type,
            **({"profile_image": profile_image} if user_ref and profile_image else {}),
            "display_name": convert_to_html_entities(display_name),
            **({"link": owner_link} if user_ref else {})
        },
        "is_accepted": is_accepted,
        **({"community_owned_date": community_owned_date} if comm_owned else {}),
        "score": int(score),
        "last_activity_date": last_activity_date,
        **({"last_edit_date": last_edit_date} if is_edited else {}),
        "creation_date": creation_date,
        "answer_id": int(id),
        "question_id": int(question_id),
        **({"body": body} if withbody else {})
    })

    return answer_data


@app.route('/questions/<ids>/answers', methods=['GET', 'POST'])
def api_answers(ids):
    params = {key: [value] for key, value in request.args.to_dict().items()}
    id = ids.split(";")
    ids = list(dict.fromkeys(id))  # Removes duplicates while preserving order
    out = scrape_answers(ids, params)
    json_out = json.dumps(out, indent=2)
    print(json_out)
    return Response(json_out, content_type='application/json')


def scrape_answers(ids, params):
    site = params.get("site")
    if not site or site[0] != "stackoverflow":
        return {"error": "The 'site' parameter is required."}

    # check built in filters
    filter = params.get("filter")
    if filter:
        if filter[0] == "none":
            # print(json.dumps("{}", indent=2))
            return {}

    # Initialize data structure
    answers_data = {
        "items": [],
        "has_more": False
    }

    for id in ids:
        base_url = 'https://stackoverflow.com/questions'
        post_url = base_url + "/" + id + "?noredirect=anything"
        post_soup = test_request(post_url)
        answers_tag = post_soup.find('div', id='answers')
        pattern = re.compile(r'^answer-\d+$')

        if not answers_tag:
            # print(json.dumps(answers_data, indent=2))
            return answers_data

        # if multiple answer pages
        help = post_soup.find('div', class_="s-pagination site1 themed pager-answers")
        if help:
            last_page = help.get_text().split()[-2]
            for num in range(1, int(last_page) + 1):
                post_soup = test_request(post_url+"&page="+str(num))
                answers_tag = post_soup.find('div', id='answers')
                pattern = re.compile(r'^answer-\d+$')
                answers = answers_tag.find_all(id=pattern)

                for answer in answers:
                    data_list = get_answers_data(answer['data-answerid'], post_soup, params)
                    answers_data['items'].extend(data_list)

        else:
            answers = answers_tag.find_all(id=pattern)

            for answer in answers:
                data_list = get_answers_data(answer['data-answerid'], post_soup, params)
                answers_data['items'].extend(data_list)


    filtered_answers_data = sort_data(answers_data, params)

    if filter:
        if filter[0] == "total":
            out = {"total": len(filtered_answers_data["items"])}
            return out

    # Print or return the JSON structure
    # print(json.dumps(filtered_answers_data, indent=2))
    return filtered_answers_data


def get_revision_question(id, type):
    revision_url = 'https://stackoverflow.com/posts/' + str(id) + "/revisions/?page="
    num = 0
    not_found = True
    if type == 'community':
        tag = 'Post Made Community Wiki'
    elif type == 'locked':
        tag = 'Post Locked'
    elif type == 'protected':
        tag = 'Question Protected'

    while not_found:
        num = num + 1
        revision_soup = test_request(revision_url + str(num))
        sections = revision_soup.find_all('div', class_="mb12 js-revision")
        for element in sections:
            if element.get_text(strip=True).__contains__(tag):
                time_tag = element.find('div', class_="s-user-card--time")
                date_tag = time_tag.find("span", title=True)
                date = convert_to_epoch(date_tag['title'])
                return date
            if type == "protected" and element.get_text(strip=True).__contains__("Question Unprotected"):
                return
            tag_num = element.find("div", title="revision 1")
            if tag_num:
                not_found = False
    return


def convert_body_to_html_entities(html_text):
    # Parse the HTML content
    soup = BeautifulSoup(html_text, 'html.parser')

    # Function to encode text while preserving HTML tags
    def encode_text(element):
        new_content = []
        for part in element.contents:
            if isinstance(part, str):
                # Encode plain text, leaving double quotes within attributes unencoded
                encoded_part = html.escape(part, quote=False)
                encoded_part = encoded_part.replace('"', '&quot;')
                new_content.append(encoded_part)
            else:
                # Append other parts (like tags) without modification
                new_content.append(part)
        element.clear()
        element.extend(new_content)

    # Apply encoding to all <p> tags
    for p_tag in soup.find_all('p'):
        encode_text(p_tag)

    # Convert the soup object back to a string and handle <br/> tags
    html_str = str(soup)
    html_str = html_str.replace('<br/>', '<br>')

    return html_str

def convert_to_html_entities(text):

    escaped_text = html.escape(text)
    return escaped_text


def url_params(params):
    # sorting
    sort = params.get("sort")
    tagged = params.get("tagged")

    url = "https://stackoverflow.com/questions"
    if tagged:
        url += "/tagged/" + tagged[0].replace(";", " ")
    url += "?"

    if sort:
        if sort[0] == "activity":
            url += "&sort=RecentActivity"
        elif sort[0] == "votes":
            url += "&sort=votes"
        elif sort[0] == "creation":
            url += "&sort=Newest"
        elif sort[0] == "hot":
            return "https://stackoverflow.com/?tab=hot"
        elif sort[0] == "week":
            return "https://stackoverflow.com/?tab=week"
        elif sort[0] == "month":
            return "https://stackoverflow.com/?tab=month"
    else:
        url += "&sort=RecentActivity"

    return url


def sort_data(question_data, params):
    fromdate = params.get("fromdate")
    todate = params.get("todate")
    max = params.get("max")
    min = params.get("min")
    sort = params.get("sort")
    order = params.get("order")
    page = params.get("page")
    pagesize = params.get("pagesize")

    # Initialize empty data structure
    empty_data = {
        "items": [],
        "has_more": False
    }

    if not pagesize:
        pagesize = [30]

    if order:
        if order[0] == "desc":
            ord = True
        else:
            ord = False
    else:
        ord = True

    if not sort:
        sort = ["activity"]

    # Filter items based on constraints
    filtered_items = []
    for item in question_data["items"]:
        if fromdate:
            if int(fromdate[0]) < int(item["creation_date"]):
                continue
        if todate:
            if int(todate[0]) > int(item["creation_date"]):
                continue
        if max:
            if sort[0] == "activity":
                if int(max[0]) < int(item["last_activity_date"]):
                    continue
            elif sort[0] == "votes":
                if int(max[0]) < int(item["score"]):
                    continue
            elif sort[0] == "creation":
                if int(max[0]) < int(item["creation_date"]):
                    continue
        if min:
            if sort[0] == "activity":
                if int(min[0]) > int(item["last_activity_date"]):
                    continue
            elif sort[0] == "votes":
                if int(min[0]) > int(item["score"]):
                    continue
            elif sort[0] == "creation":
                if int(min[0]) > int(item["creation_date"]):
                    continue

        filtered_items.append(item)

    # Add valid items to array
    question_data["items"] = filtered_items

    # Sort the array correctly
    if sort[0] == "activity":
        question_data["items"].sort(key=lambda x: int(x["last_activity_date"]), reverse=ord)
    elif sort[0] == "votes":
        question_data["items"].sort(key=lambda x: int(x["score"]), reverse=ord)
    elif sort[0] == "creation":
        question_data["items"].sort(key=lambda x: int(x["creation_date"]), reverse=ord)

    # Paging
    if int(pagesize[0]) == 0:
        if len(question_data["items"]) > 0:
            empty_data["has_more"] = True
        return empty_data
    pages = [question_data["items"][i:i + int(pagesize[0])] for i in
             range(0, len(question_data["items"]), int(pagesize[0]))]
    if not pages:
        return empty_data
    if page:
        if int(page[0]) - 1 >= len(pages):
            return empty_data
        if len(pages) > int(page[0]):
            question_data["has_more"] = True
        question_data["items"] = pages[int(page[0]) - 1]
        return question_data
    else:
        if len(pages) > 1:
            question_data["has_more"] = True
        question_data["items"] = pages[0]
        return question_data



@backoff.on_exception(backoff.expo, requests.exceptions.RequestException)
def request_backoff(url):
    time.sleep(1)
    response = requests.get(url, verify=False)
    print(response)

    # Skip retrying for 404 errors
    if response.status_code == 404:
        return response.text

    response.raise_for_status()  # Raise an error for bad responses
    return response.text


def test_request(url):
    try:
        html_content = request_backoff(url)
        soup = BeautifulSoup(html_content, 'html.parser')  # Parse the HTML content
        return soup
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")

def get_migrated_data(id):
    revision_url = 'https://stackoverflow.com/posts/' + str(id) + "/revisions/?page="
    num = 0
    not_found = True
    date = None
    question_id = None
    site_url_cut = None

    while not_found:
        num = num + 1
        revision_soup = test_request(revision_url + str(num))
        sections = revision_soup.find_all('div', class_="mb12 js-revision")
        for element in sections:
            if element.get_text(strip=True).__contains__("Post Migrated Here") and not_found == True:
                time_tag = element.find('div', class_="s-user-card--time")
                date_tag = time_tag.find("span", title=True)
                date = convert_to_epoch(date_tag['title'])

                site_url_tag = element.find('a', href=True)
                if site_url_tag:
                    site_url = site_url_tag['href']
                    match = re.search(r'/(\d+)', site_url)
                    site_url_cut = requests.get(site_url).url
                    site_url_cut = site_url_cut.split(".com")[0] + ".com"
                    if match:
                        question_id = match.group(1)
                    else:
                        question_id = None  # Handle the case where the question ID is not found

            tag_num = element.find("div", title="revision 1")
            if tag_num:
                not_found = False

    data = {
        **({"other_site": {"site_url": site_url_cut}} if site_url_cut else {}),
        **({"on_date": date} if date else {}),
        **({"question_id": question_id} if question_id else {}),
    }

    return data


def comm_bot_activity_date(id):
    revision_url = 'https://stackoverflow.com/posts/' + str(id) + "/revisions/?page="
    num = 0
    not_found = True

    while not_found:
        num = num + 1
        revision_soup = test_request(revision_url + str(num))
        sections = revision_soup.find_all('div', class_="mb12 js-revision")

        for i, element in enumerate(sections):
            card_info = element.find("div", class_="s-user-card--info")
            if card_info and "Bot" in card_info.get_text(strip=True):
                has_href = card_info.find('a', href=True)
                if not has_href:
                    if i + 1 < len(sections):
                        next_element = sections[i + 1]
                        new_time_tag = next_element.find('div', class_="s-user-card--time")
                        if new_time_tag:
                            date_span = new_time_tag.find('span', title=True)
                            if date_span:
                                date = date_span["title"]
                                date = convert_to_epoch(date)
                                return date
                    not_found = False
                else:
                    if has_href.get_text(strip=True).__contains__("Community"):
                        time_tag = element.find('div', class_="s-user-card--time")
                        if time_tag.get_text(strip=True).__contains__("approved"):
                            date_tag = time_tag.find("span", title=True)
                            date = convert_to_epoch(date_tag['title'])
                            return date
                        else:
                            next_element = sections[i + 1]
                            new_time_tag = next_element.find('div', class_="s-user-card--time")
                            if new_time_tag:
                                date_span = new_time_tag.find('span', title=True)
                                if date_span:
                                    date = date_span["title"]
                                    date = convert_to_epoch(date)
                                    return date
                            not_found = False


            tag_num = element.find("div", title="revision 1")
            if tag_num:
                not_found = False

    return None


# main driver function
if __name__ == '__main__':
    port = int(os.getenv('STACKOVERFLOW_API_PORT', 5000))

    # run() method of Flask class runs the application
    # on the local development server.
    app.run(port=port)