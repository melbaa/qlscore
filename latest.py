import json
import concurrent.futures
import traceback
import functools
import operator
import urllib.request

from tkinter import *
from tkinter import ttk
from tkinter import filedialog

"""
http://www.tkdocs.com/tutorial/index.html
http://www.tcl.tk/man/tcl8.5/
"""


url_prefix = 'http://www.quakelive.com/stats/matchdetails/'
NUM_WORKERS = 10  # how many requests to make at the same time
TIMEOUT = 60  # seconds to wait before a request times out

"""
the urllib user agent seems to be banned, I guess they have their reasons.
"""
USER_AGENT = "Mozilla/5.0"

def line_from_args(*args):
    """
    line_from_args('hello', 'world') -> 'hello world '
    """
    line = ''
    for arg in args:
        line += str(arg) + ' '
    return line


def load_url(url, timeout):
    headers = {'User-Agent': USER_AGENT}
    req = urllib.request.Request(url, headers=headers)
    conn = urllib.request.urlopen(req, timeout=timeout)
    txt = conn.readall().decode('utf8')
    json_reply = json.loads(txt)
    return json_reply


def get_game_ids(games):
    game_ids = []
    for line in games.split('\n'):
        line = line.strip()
        if line == '':
            continue
        if line[0] == '#':
            continue

        game_ids.append(line)
    return game_ids


def make_game_urls(game_ids):
    for id in game_ids:
        yield url_prefix + id


def make_requests(urls):
    """
    pull json data out of urls and add the 'mel_game_id' = url key, which is useful
    for error messages for users
    """

    json_replies = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=NUM_WORKERS) as ex:
        future_to_url = {
            ex.submit(load_url, url, TIMEOUT): url for url in urls}
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                data = future.result()
                data['mel_game_id'] = url
                json_replies.append(data)

            except Exception as exc:
                print('%r generated an exception: %s' % (url, exc))
                raise

    return json_replies


class FFA1:

    def __init__(self):
        self.player_scores = dict()

    def calculate(self, games_json_stats):
        """
          games_json_stats - a list of json data, pulled from quakelive.com,
          with stats such as ingame score, player models, accuracies,
          damage delivered etc.
          For an example see FFA1.json

          returns a list of lines without the newline characters,
          that the user will see

          throwing an exception will show an error message to the user, so
          it's good to show at least what's being processed, before the error
          happens.
        """

        for game in games_json_stats:

            yield ''
            yield 'looking at the game '
            yield game['mel_game_id']
            yield ''

            mapname = game['MAP_NAME_SHORT']
            yield line_from_args('map', mapname)

            scores = game['SCOREBOARD']

            uniq_scores = set()
            place = -1
            for score in scores:

                nick = score['PLAYER_NICK']
                ingame_score = score['SCORE']

                if ingame_score not in uniq_scores:
                    place += 1
                    uniq_scores.add(ingame_score)

                if nick not in self.player_scores:
                    self.player_scores[nick] = 0

                points = 1600 - place * 100
                self.player_scores[nick] += points
                yield line_from_args(nick, ingame_score, points)

            if 'SCOREBOARD_QUITTERS' in game:
                yield 'QUITTERS:'
                quit_scores = game['SCOREBOARD_QUITTERS']

                for score in quit_scores:
                    yield line_from_args(score['PLAYER_NICK'], score['SCORE'])

        yield ''
        yield "TOTALS"

        for nick in sorted(self.player_scores, key=self.player_scores.get, reverse=True):

            yield line_from_args(nick, self.player_scores[nick])


class FFA2:

    def __init__(self):
        self.player_totals = dict()

    def calculate(self, games_json_stats):
        """


        #ties
        cfd62c38-e6ce-11e3-b603-00259031fd90/ffa/1

        #quitters
        d5cb0194-e69d-11e3-b603-00259031fd90/ffa/1

        b9874e26-e5b6-11e3-a44f-00259031fd90/ffa/1

        f8577342-e5de-11e3-a44f-00259031fd90/ffa/1

        """

        for game in games_json_stats:
            player_data = []

            yield ''
            yield 'looking at the game '
            yield game['mel_game_id']
            yield ''

            mapname = game['MAP_NAME_SHORT']
            yield line_from_args('map', mapname)
            yield "score, kills, dmg, deaths, nick"

            scores = game['SCOREBOARD']
            quitters_attr = 'SCOREBOARD_QUITTERS'
            if quitters_attr in game:
                scores.extend(game[quitters_attr])
            for score in scores:
                nick = score['PLAYER_NICK']
                nick_score = int(score['SCORE'])
                #frags (kills)
                kills = int(score['KILLS'])
                dmg = int(score['DAMAGE_DEALT'])
                deaths = int(score['DEATHS'])

                tup = (nick_score, kills, dmg, deaths, nick)
                player_data.append(tup)

            """
      sort records for game
      stable sort, so we can sort multiple times, by sorting from least
        to most important fields
      alternative is to write a comparator and use functools.cmp_to_key
      """
            player_data.sort(key=operator.itemgetter(3))
            player_data.sort(key=operator.itemgetter(2), reverse=True)
            player_data.sort(key=operator.itemgetter(1), reverse=True)
            player_data.sort(key=operator.itemgetter(0), reverse=True)

            max = 1600
            for player in player_data:
                yield line_from_args(str(player), max)
                nick_score, kills, dmg, deaths, nick = player
                if nick not in self.player_totals:
                    self.player_totals[
                        nick] = max, nick_score, kills, dmg, deaths, nick
                else:
                    total_pts, total_nick_score, total_kills, total_dmg, total_deaths \
                        , nick = self.player_totals[nick]
                    total_pts += max
                    total_nick_score += nick_score
                    total_kills += kills
                    total_dmg += dmg
                    total_deaths += deaths
                    self.player_totals[nick] = total_pts, total_nick_score, total_kills \
                        , total_dmg, total_deaths, nick
                max -= 100

        yield ''
        yield 'TOTALS'
        yield 'nick pts game_score kills dmg deaths'
        player_totals_list = []
        for nick in self.player_totals:
            player_totals_list.append(self.player_totals[nick])

        # more weird stable sort abuse
        player_totals_list.sort(key=operator.itemgetter(4))
        player_totals_list.sort(key=operator.itemgetter(3), reverse=True)
        player_totals_list.sort(key=operator.itemgetter(2), reverse=True)
        player_totals_list.sort(key=operator.itemgetter(1), reverse=True)
        player_totals_list.sort(key=operator.itemgetter(0), reverse=True)

        for player in player_totals_list:
            pts, score, kills, dmg, deaths, nick = player
            yield line_from_args(nick, pts, score, kills, dmg, deaths)


# map ruleset strings to ruleset implementations
# those strings are selectable in the GUI

ruleset_default = 'FFA2'
ruleset_map = {'FFA1': FFA1, 'FFA2': FFA2}

# GUI


def calculate():
    games = inputtext.get('1.0', 'end')
    game_ids = get_game_ids(games)
    urls = make_game_urls(game_ids)
    games_json_stats = make_requests(urls)

    ruleset_string = rulesets.get()
    ruleset = ruleset_map[ruleset_string]()
    output = ruleset.calculate(games_json_stats)

    outputtext.delete('1.0', 'end')

    try:
        for line in output:
            outputtext.insert('end', line + '\n')

    except Exception as e:
        traceback.print_exc()
        output = ['An error occured', str(type(e)),  
	    str(e), '', 'Is the game ID correct?', 
	    'Are you looking at an old game, not in history anymore?']
        for line in output:
            outputtext.insert('end', line + '\n')


def saveas():
    intxt = inputtext.get('1.0', 'end')
    outtxt = outputtxt.get('1.0', 'end')
    filename = filedialog.asksaveasfilename()

    if not filename:
        return

    with open(filename, 'w') as f:
        f.write('ruleset\n\n')
        f.write(rulesets.get() + '\n')
        f.write('\n\ninput\n\n')
        f.write(intxt)
        f.write('\n\noutput\n\n')
        f.write(outtxt)

root = Tk()
root.title("Group score calculator by melba")


main = ttk.Frame(root)
main['padding'] = (5, 5, 5, 5)


leftpane = ttk.Frame(main)
rightpane = ttk.Frame(main)

rulelabel = ttk.Label(leftpane, text='pick a ruleset')

# what do display in the ruleset picker
rules = [rule for rule in sorted(ruleset_map)]
rulesetvar = StringVar()
rulesetvar.set(ruleset_default)
rulesets = ttk.Combobox(leftpane, textvariable=rulesetvar)
rulesets['values'] = rules
rulesets['state'] = 'readonly'
rulesets['width'] = 70

label = ttk.Label(leftpane, text='enter game ids')


inputtext = Text(leftpane, wrap='word')
inputscroll = ttk.Scrollbar(leftpane, orient=VERTICAL, command=inputtext.yview)
inputtext.configure(yscrollcommand=inputscroll.set)
inputtext.see('1.0')
inputtext['width'] = 50

exampletxt = """\
#lines starting with # are comments
#empty lines are allowed, they are skipped

ef37ffd0-8c55-11e3-bd9c-00259031fd90
314da4cc-8c53-11e3-bd9c-00259031fd90/ffa/1
f8c5ffc6-8c54-11e3-bd9c-00259031fd90/ffa/1
30ce7766-8c52-11e3-bd9c-00259031fd90/ffa/1

#example game where all players quit
#50845138-9310-11e3-a362-00259031fd90/ffa/1
"""

inputtext.insert('1.0', exampletxt)

btn = ttk.Button(leftpane, text='calculate', command=calculate)


main.grid(row=0, column=0, sticky=N + W + E + S)
root.rowconfigure(0, weight=1)
root.columnconfigure(0, weight=1)
main.rowconfigure(0, weight=1)
main.columnconfigure(0, weight=1)
main.columnconfigure(1, weight=1)


leftpane.grid(row=0, column=0, sticky=N + S + E + W)
leftpane.rowconfigure(3, weight=1)
leftpane.columnconfigure(0, weight=1)

rulelabel.grid(row=0, column=0)
rulesets.grid(row=1, column=0, sticky=N)
label.grid(row=2, column=0)
inputtext.grid(row=3, column=0, sticky=N + S + E + W)
inputscroll.grid(row=3, column=1, sticky=[N, S])
btn.grid(row=4, column=0)


outputtext = Text(rightpane)
outputtext['width'] = 50
outlabel = ttk.Label(rightpane, text='scores')
outtextscroll = ttk.Scrollbar(
    rightpane, orient=VERTICAL, command=outputtext.yview)
outputtext.configure(yscrollcommand=outtextscroll.set)
outputtext.see('1.0')
saveasbtn = ttk.Button(rightpane, text='save as', command=saveas)


rightpane.grid(row=0, column=1, sticky=N + S + E + W)
# rightpane.rowconfigure(0,weight=1)
rightpane.rowconfigure(1, weight=1)
rightpane.columnconfigure(0, weight=1)

outlabel.grid(row=0, column=0)
outputtext.grid(row=1, column=0, sticky=N + S + E + W)
outtextscroll.grid(row=1, column=1, sticky=N + S)
saveasbtn.grid(row=2, column=0)

root.mainloop()
