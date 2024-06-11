import requests
import json
import time
import re
import os

# TODO: function for making the "other half" of char cards (user cards basically).
# Should prompt a model to create an appropriate counter party to the role play (if its a milf and shota, make a shota. a slave and master, make a master)
# name and brief description of them and how they will act
# embed this data in the card so it can be easily used in the future
# maybe make an array of objects? [{name: bluefish description: loves to swim}, {name: redfish description: hates your mom}]

def settings_loader():
    with open('settings.json') as file:
        settings = json.load(file)

    return settings

settings = settings_loader()

# TODO: options for what slop to load in
def slop_list_loader():
    with open('slop.json') as file:
        data = json.load(file)

    slop_list = []

    for key in data:
        slop_list.extend(data[key])

    return slop_list

slop_list = slop_list_loader()

# Used to check if a string contains any of these stings. If they do, return True, if not return False
# check for things like "{{{user}}} said" when the bot responds? Maybe not in this function tho
def slop_check(string):
    for slop_item in slop_list:
        if re.search(slop_item, string, re.IGNORECASE):
            return True
        # no slop was found, return false
        return False
    
# unused
# Used to get the token count from the KCPP model
# TODO: what about if I'm using horde?
def get_token_count(string):
    tokencount_response = (
        requests.post(
            f"http://127.0.0.1:5001/api/extra/tokencount",
            json={"prompt": string},
        ).json()["value"]
    )

    return tokencount_response

def setup_stop_sequences(first_character, second_character):
    system_tag = "### System:\n"
    user_tag = "\n\n### Instruction:\n"
    model_tag = "\n\n### Response:\n"

    stop_sequences = [
        system_tag.strip(),
        user_tag.strip(),
        model_tag.strip(),
        f"{first_character}:",
        f"{second_character}:"
    ]

    return stop_sequences

# TODO: decide if I can reuse this function for evaluating messages or entire logs
def generate_a_chat_message(system_prompt, chat_history, stop_sequences):
    # TODO: finish writing the horde section
    if settings["log_gen"]["api_link"] == "horde":
        response = "blank"

        return response

    else: # if not using horde make request to the api_link # TODO: figure out if this really is the oai api
        response = requests.post(
            settings["log_gen"]["api_link"],
            json={
                "prompt": f"{system_prompt}\n{chat_history}",
                "stop_sequence": stop_sequences,
                **settings["log_gen"]["generation_settings"],
            }
        ).json()["results"][0]["text"]

    # Removes the stop sequence, since kobold doesn't remove it
    for stop_sequence in stop_sequences:
        response = response.replace(stop_sequence, "").strip()

    return response

# TODO: first build "simple" mode, while leaving a "live eval" mode easy to add on
# TODO: keep track of message_regen_count as an array, indexed to the position of each message. First in each array will be 0 for the first message in card
def generate_next_chat_message(system_prompt, chat_history, stop_sequences, current_char, next_char):
    # TODO: keep regex rejects in an array of arrays
    message_rejects = []

    message_regen_count = 0
    while True:
        # generates a message to run checks against, and removes eos
        generated_message = generate_a_chat_message(system_prompt, chat_history, stop_sequences)

        # TODO: check for excessive looping (...I...I...I...I)
        # TODO: check if token length is close to last message/few messages?
        # TODO: should I reject generation if it got cut off
        # TODO: make sure there is punctuation at the end of the message

        # TODO: figure out if this works, chatgpt wrote this section
        if (
            slop_check(generated_message) is True or
            len(generated_message) < 15 or  # Trigger if character count is not > 15
            generated_message.count('"') % 2 != 0 or  # Trigger if quotes are not closed
            any(f"{next_char} {action}".lower() in generated_message.lower() for action in settings["impersonating_actions"]) or  # Trigger if other char is speaking when it's not their turn
            f". {next_char} ".lower() in generated_message.lower() or
            f'" {next_char} '.lower() in generated_message.lower() or 
            generated_message.endswith("...")
        ):
            # message contains slop or is otherwise regex banned, rejected.
            message_regen_count += 1
            # TODO: add the objects to the message reject array
            if message_regen_count > settings["log_gen"]["max_rerolls"]:
                return None, message_rejects, message_regen_count
            else:
                continue

        # TODO: optional ai check/comparisons
        
        # message is at least adequate, maybe the best of all candidates. loop is over
        else: 
            return generated_message, message_rejects, message_regen_count


# TODO: keep track of output_log (sharegpt) and chat (the history that gets sent to the model)
# TODO: grab the model_name and live_eval_model_name from the api and save it, rather then passing them in manually
def generate_whole_log(card, human_index_num, model_name, live_eval_model_name):
    # setup card/system prompt
    system_prompt = card["data"]['description'] # TODO: format properly
    chat_history = card["data"]["first_mes"] # this might not be right

    # Load custom "human" card to be the bot's rp partner. 
    # This data is not included in cards by default and needs to be generated and inserted into each bot card before hand
    human_card = card["human_cards"][human_index_num] # will this grab the object in the array?

    # keep track of output_log (sharegpt) and chat (the history that gets sent to the model)
    output_log = [
        {"from": "system", "value": system_prompt}
    ]
    chat_history = ""

    # first array needs to be added and is always empty, because the 0th message is defined by the char card
    message_reject_array = [[]]

    # Can I use the same stop sequences the whole chat?
    stop_sequences = setup_stop_sequences(human_card["data"]["name"], card["data"]["name"])

    # loops until a message errors out from too many regens or we hit the max_turns
    while len(chat_history) < settings["log_gen"]["max_turns"]:
        # add correct [character name]: (depending on if number of messages is odd or even?)
        # feed proper stop tokens (name, etc)
        # feed proper turns (maybe based on if loop i is even or odd)

        # TODO: write this in a more clear way (maybe use the index number (output_log) instead of length?)
        # the message count will be opposite from the number in the index
        # not sure which should be odd or even this is just a pre print
        if len(chat_history) % 2 == 0: # the bot was the last one to send a message, it is now the "human's" turn
            message_from = "human"
            current_char = human_card["data"]["name"]
            next_char = card["data"]["name"]
        else:
            message_from = "gpt"
            current_char = card["data"]["name"]
            next_char = human_card["data"]["name"]

        # call generate_next_chat_message and check it didn't return a None value
        response, message_rejects, message_regen_count = generate_next_chat_message(system_prompt, chat_history, stop_sequences, current_char, next_char)
        if response == None: # could not find a good next message in the amount of max turns, breaking to save the log as being finished
            break

        # add to both the sharegpt log and the chat history (what gets fed to the model)
        output_log.append(
            {
            "from": message_from,
            "name": current_char,
            "value": response # TODO: strip out extra data, like name: or instruct tags
            }
        )

        message_reject_array.append(message_rejects) # add the rejects for this turn to the array of all rejects

        chat_history += current_char+": "+response+"\n" # TODO: is this the proper way to do it # TODO: also maybe strip char_name + \n from output_log
        # abort loop and finish if response is None or if settings["max_turns"] is met
        if message_regen_count > settings["log_gen"]["max_rerolls"]:
            break

    # TODO: below might be better if I separated it out as its own function

    # format log, save to a json file, maybe have option to eval with a model
    log_json = {
        "card": card,
        "human_card": human_card,
        "model": model_name,
        "final_log": output_log,
        "message_reject_array": message_reject_array,
        "live_eval": settings["do_eval_messages"],
        "live_eval_model": live_eval_model_name
    }
    timestamp = time.datetime.now().strftime("%s")
    save_name = f"{card['data']['creator']} - {card['data']['name']} ({model_name}) ({timestamp}).json"
    save_path = os.path.join(settings["log_gen"]["save_folder"], save_name)
    with open(save_path, "w") as f:
        json.dump(log_json, f, indent=4)

    return


def main_loop():
    # feed cards to all the threads
    # track what cards/first messages have been feed to threads (by saving as a json?)


    return