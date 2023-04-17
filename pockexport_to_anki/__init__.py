import json
import os
import os.path
import pocket
import requests
import sys

import importlib.machinery
import importlib.util

# Load secrets from pockexport for use by pocket module.
loader = importlib.machinery.SourceFileLoader(
      'secrets', os.path.expanduser('~/.config/pockexport/secrets.py'))
spec = importlib.util.spec_from_loader('secrets', loader)
secrets = importlib.util.module_from_spec(spec)
loader.exec_module(secrets)

anki_url = "http://localhost:8765"
version = 6

def main():
   with open(sys.argv[1]) as f:
      data = json.load(f)

   deck_name = 'Articles'
   note_type = 'Pocket Article'
   suspend_cards = set()
   unsuspend_cards = set()
   archive_items = set()
   readd_items = set()
   favorite_items = set()
   marked_notes = set()
   unfavorite_items = set()
   unmarked_notes = set()
   try:
      for item in data['list'].values():
         try:
            tags = list(item['tags'].keys())
         except KeyError:
            tags = []
         fields = {
            'item_id': item['item_id'],
            'given_url': item.get('given_url', ''),
            'given_title': item.get('given_title', ''),
            'resolved_url': item.get('resolved_url', ''),
            'resolved_title': item.get('resolved_title', ''),
            'time_added': item.get('time_added', ''),
            'word_count': item.get('word_count', ''),
            'time_to_read': str(item.get('time_to_read', '')),
            'excerpt': item.get('excerpt', ''),
         }

         payload = {
            "action": "findNotes",
            "version": version,
            "params": {
               "query": f"item_id:{item['item_id']}",
            },
         }
         response = json.loads(requests.post(anki_url, json=payload).text)
         notes_existing = response['result']
         note_id = None
         mod_time = 0
         if notes_existing:
            note_id = notes_existing[0]
            payload = {
               "action": "findCards",
               "version": version,
               "params": {
                  "query": f"nid:{note_id}",
               },
            }
            response = json.loads(requests.post(anki_url, json=payload).text)
            #print(response)
            cards = response['result']
            payload = {
               "action": "cardsModTime",
               "version": version,
               "params": {
                  "cards": cards,
               },
            }
            response = json.loads(requests.post(anki_url, json=payload).text)
            #print(response)
            mod_time = max(x["mod"] for x in response['result'])

            payload = {
               "action": "updateNoteFields",
               "version": version,
               "params": {
                  "note": {
                     "id": note_id,
                     "fields": fields,
                  }
               }
            }
            response = json.loads(requests.post(anki_url, json=payload).text)
            if (response['error'] is not None):
               print(item)
            #print(response)

         else:
            payload = {
               "action": "addNote",
               "version": version,
               "params": {
                  "note": {
                     "deckName": deck_name,
                     "modelName": note_type,
                     "fields": fields,
                     "tags": tags,
                  }
               }
            }
            response = json.loads(requests.post(anki_url, json=payload).text)
            if (response['error'] is not None
                and response['error'] !=
                "cannot create note because it is a duplicate"):
               print(item)
               print(response)
               continue
            #print(response)
            note_id = response['result']

         payload = {
            "action": "notesInfo",
            "version": version,
            "params": {
               "notes": [note_id],
            },
         }
         response = json.loads(requests.post(anki_url, json=payload).text)
         #print(response)
         note_info = response['result'][0]
         tags = note_info['tags']
         note_favorited = "marked" in tags
         if note_favorited and item['favorite'] == "0":
            if int(item.get('time_favorited', '0')) > mod_time:
               unmarked_notes |= {note_id}
            else:
               favorite_items |= {item['item_id']}
         elif not note_favorited and item['favorite'] == "1":
            if int(item.get('time_favorited', '0')) > mod_time:
               marked_notes |= {note_id}
            else:
               unfavorite_items |= {item['item_id']}

         payload = {
            "action": "findCards",
            "version": version,
            "params": {
               "query": f"item_id:{item['item_id']}",
            },
         }
         response = json.loads(requests.post(anki_url, json=payload).text)
         cards = response['result']
         if cards is None:
            print(response)
            continue
         if mod_time < int(item.get('time_read', '0')):
            if item.get('status', '0') == '1' and not (
                  item['item_id'] in favorite_items or note_favorited):
               suspend_cards |= set(cards)
            else:
               unsuspend_cards |= set(cards)
         else:
            payload = {
               "action": "areSuspended",
               "version": version,
               "params": {
                  "cards": cards,
               },
            }
            response = json.loads(requests.post(anki_url, json=payload).text)
            for card, is_suspended in zip(cards, response['result']):
               if not is_suspended and not note_favorited and item.get('status', '0') == '1':
                  readd_items |= {item['item_id']}
               elif is_suspended and item.get('status', '0') == '0':
                  archive_items |= {item['item_id']}
   except KeyboardInterrupt:
      pass

   payload = {
      "action": "suspend",
      "version": version,
      "params": {
         "cards": list(suspend_cards),
      },
   }
   print(payload)
   response = json.loads(requests.post(anki_url, json=payload).text)
   print(response)
   payload = {
      "action": "unsuspend",
      "version": version,
      "params": {
         "cards": list(unsuspend_cards),
      },
   }
   print(payload)
   response = json.loads(requests.post(anki_url, json=payload).text)
   print(response)

   payload = {
      "action": "addTags",
      "version": version,
      "params": {
         "notes": list(marked_notes),
         "tags": "marked",
      },
   }
   print(payload)
   response = json.loads(requests.post(anki_url, json=payload).text)
   print(response)
   payload = {
      "action": "removeTags",
      "version": version,
      "params": {
         "notes": list(unmarked_notes),
         "tags": "marked",
      },
   }
   print(payload)
   response = json.loads(requests.post(anki_url, json=payload).text)
   print(response)

   payload = {
      "action": "sync",
      "version": version,
   }
   print(payload)
   response = json.loads(requests.post(anki_url, json=payload).text)
   print(response)

   print("Pocket API (NYI)")
   print(f"favorite_items: {favorite_items}")
   print(f"unfavorite_items: {unfavorite_items}")
   print(f"archive_items: {archive_items}")
   print(f"readd_items: {readd_items}")
