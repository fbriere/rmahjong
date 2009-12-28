# Copyright (C) 2009 Stanislav Bohm 
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; see the file COPYING. If not, see 
# <http://www.gnu.org/licenses/>.

import logging
from copy import copy

from connection import ConnectionClosed
from tile import Tile, Pon, Chi
from eval import count_of_tiles_yaku, find_potential_chi, hand_in_tenpai
from botengine import BotEngine

class Player:

	def __init__(self, server, name):
		self.name = name
		self.server = server
		self.score = 25000
		self.can_drop_tile = False
		self.drop_zone = []
		self.open_sets = []

	def player_round_reset(self):
		self.drop_zone = []
		self.open_sets = []
		self.can_drop_tile = False

	def set_neighbours(self, left, right, across):
		self.left_player = left
		self.right_player = right
		self.across_player = across

	def set_wind(self, wind):
		self.wind = wind

	def set_round(self, round, hand):
		self.round = round
		self.hand = hand

	def is_dealer(self):
		return self.wind.name == "WE"

	def other_players(self):
		""" Returns other players in order from right """
		return [ self.right_player, self.across_player, self.left_player ]

	def new_hand_tile(self, tile):
		self.hand.append(tile)

	def move(self, tile):
		self.new_hand_tile(tile)
		self.can_drop_tile = True

	def other_move(self, player):
		pass

	def player_dropped_tile(self, player, tile):
		pass

	def round_is_ready(self):
		logging.info("Player '%s' intial hand: %s" % (self.name, self.hand))

	def hand_actions(self):
		options = []
		if count_of_tiles_yaku(self.hand, self.open_sets, self.round.round_wind, self.wind) > 0:
			options.append("Tsumo")
		return options

	def is_furiten(self):
		# TODO
		return False

	def is_tenpai(self):
		return hand_in_tenpai(self.hand, self.open_sets)

	def steal_actions(self, player, tile):
		options = []
		if self.hand.count(tile) >= 2:
			options.append("Pon")

		if player == self.left_player:
			if find_potential_chi(self.hand, tile):
				options.append("Chi")

		if count_of_tiles_yaku(self.hand + [ tile ], self.open_sets, self.round.round_wind, self.wind) > 0 and not self.is_furiten():
			options.append("Ron")

		return options

	def round_end(self, player, looser, win_type, payment_name, scores, minipints, diffs):
		pass

	def round_end_draw(self, winners, loosers, payment_diffs):
		pass

	def stolen_tile(self, player, from_player, action, opened_set, tile):
		if player == self:
			my_set = copy(opened_set)
			my_set.closed = False

			tiles = my_set.tiles()
			tiles.remove(tile)
			for t in tiles:
				self.hand.remove(t)
	
			self.open_sets.append(my_set)
			self.can_drop_tile = True

	def drop_tile(self, tile):
		self.hand.remove(tile)
		self.drop_zone.append(tile)
		self.server.state.drop_tile(self, tile)

	def __str__(self):
		return self.name

	def __repr__(self):
		return "<P: %s>" % self.name


class NetworkPlayer(Player):

	def __init__(self, server, name, connection):
		Player.__init__(self, server, name)
		self.connection = connection
		self.potential_chi = None
		self.steal_tile = None

	def process_messages(self):
		try:
			message = self.connection.read_message()
			while message:
				self.process_message(message)
				message = self.connection.read_message()
		except ConnectionClosed, e:
			self.server.player_leaved(self)

	def tick(self):
		self.process_messages()

	def round_is_ready(self):
		Player.round_is_ready(self)
		msg = {}
		msg["message"] = "ROUND"
		msg["left"] = self.left_player.name
		msg["right"] = self.right_player.name
		msg["across"] = self.across_player.name
		msg["left_score"] = self.left_player.score
		msg["right_score"] = self.right_player.score
		msg["across_score"] = self.across_player.score
		msg["my_score"] = self.score
		msg["my_wind"] = self.wind.name
		msg["round_wind"] = self.round.round_wind.name
		msg["dora_indicator"] = self.round.dora_indicators[0].name
		msg["hand"] = " ".join( [ tile.name for tile in self.hand ] )
		self.connection.send_dict(msg)

	def move(self, tile):
		Player.move(self, tile)
		actions = " ".join(self.hand_actions())
		self.connection.send_message(message = "MOVE", tile = tile.name, actions = actions)

	def other_move(self, player):
		Player.other_move(self, player)
		self.connection.send_message(message = "OTHER_MOVE", wind = player.wind.name)

	def process_message(self, message):
		name = message["message"]

		if name == "DROP":
			if not self.can_drop_tile:
				return
			self.can_drop_tile = False
			tile = Tile(message["tile"])
			self.drop_tile(tile)
			return

		if name == "READY":
			self.server.player_is_ready(self)
			return

		if name == "STEAL":
			action = message["action"]
			if "chi_choose" in message:
				chi_tile = Tile(message["chi_choose"])
				for s, marker in self.potential_chi:
					if marker == chi_tile:
						opened_set = s
						break
			else:
				opened_set = Pon(self.steal_tile)

			self.potential_chi = None
			self.steal_tile = None
			self.server.player_try_steal_tile(self, action, opened_set)
			return

		if name == "TSUMO":
			if not self.can_drop_tile or "Tsumo" not in self.hand_actions():
				print "Tsumo is not allowed"
				return
			self.server.declare_win(self, None, "Tsumo")
			self.can_drop_tile = False
			return

		print "Unknown message " + str(message) + " from player: " + self.name

	def player_dropped_tile(self, player, tile):
		if self != player:
			actions = self.steal_actions(player, tile)
		else:
			actions = []		

		chi_choose = ""

		if actions:
			self.steal_tile = tile
			if "Chi" in actions:
				self.potential_chi = find_potential_chi(self.hand, tile)
				choose_tiles = [ t.name for set, t in self.potential_chi ]
				chi_choose = " ".join(choose_tiles)
			actions.append("Pass")

		msg_actions = " ".join(actions)
		msg = { "message" : "DROPPED", 
				"wind" : player.wind.name, 
				"tile" : tile.name, 
				"chi_choose" : chi_choose,
				"actions" : msg_actions }
		self.connection.send_dict(msg)
		
		if not actions:
			# This should be called after sending DROPPED, because it can cause new game state
			self.server.player_is_ready(self) 

	def round_end(self, player, looser, win_type, payment_name, scores, minipoints, payment_diffs):
		msg = {}
		msg["message"] = "ROUND_END"
		msg["payment"] = payment_name
		msg["wintype"] = win_type
		msg["player"] = player.wind.name
		msg["total_fans"] = sum(map(lambda r: r[1], scores))
		msg["minipoints"] = minipoints
		msg["score_items"] = ";".join(map(lambda sc: "%s %s" % (sc[0], sc[1]), scores))

		for player in self.server.players:
			msg[player.wind.name + "_score"] = player.score 
			msg[player.wind.name + "_payment"] = payment_diffs[player]
	
		self.connection.send_dict(msg)

	def round_end_draw(self, winners, loosers, payment_diffs):
		msg = {}
		msg["message"] = "DRAW"
		msg["tenpai"] = " ".join((player.wind.name for player in winners))
		msg["not_tenpai"] = " ".join((player.wind.name for player in loosers))

		for player in self.server.players:
			msg[player.wind.name + "_score"] = player.score 
			msg[player.wind.name + "_payment"] = payment_diffs[player]

		self.connection.send_dict(msg)
	
	def stolen_tile(self, player, from_player, action, opened_set, stolen_tile):
		Player.stolen_tile(self, player, from_player, action, opened_set, stolen_tile)
		msg = { "message" : "STOLEN_TILE",
				"action" : action,
				"player" : player.wind.name,
				"from_player" : from_player.wind.name,
				"tiles" : " ".join([tile.name for tile in opened_set.tiles()]),
				"stolen_tile" : stolen_tile.name
		}
		self.connection.send_dict(msg)

	def server_quit(self):
		pass


bot_names = (name for name in [ "Panda", "StormMaster", "Yogi" ])


class BotPlayer(Player):

	def __init__(self, server):
		Player.__init__(self, server, bot_names.next())
		self.engine = BotEngine()
		self.action = None

	def tick(self):
		if self.action:
			self.action()

	def server_quit(self):
		self.engine.shutdown()

	def move(self, tile):
		Player.move(self, tile)

		actions = " ".join(self.hand_actions())
		if "Tsumo" in actions:
			self.server.declare_win(self, None, "Tsumo")
			return

		self._set_basic_state()
		self.engine.question_discard()
		self.action = self.action_discard

	def action_discard(self):
		tile = self.engine.get_tile()
		if tile:
			self.action = None
			self.drop_tile(tile)

	def action_steal(self):
		set_or_pass = self.engine.get_set_or_pass()
		if set_or_pass:
			self.action = None
			if set_or_pass == "Pass":
				self.server.player_is_ready(self)
			else:
				self.server.player_try_steal_tile(self, set_or_pass.get_name(), set_or_pass)

	def _set_basic_state(self):
		self.engine.set_hand(self.hand)
		self.engine.set_wall(self.round.hidden_tiles_for_player(self))
		self.engine.set_sets(self.open_sets)
		self.engine.set_turns(self.round.get_remaining_turns_for_player(self))

	def player_dropped_tile(self, player, tile):
		if self != player:
			actions = self.steal_actions(player, tile)
			if "Ron" in actions:
				self.server.player_try_steal_tile(self, "Ron", None)
			elif actions:
				sets = []
				if "Pon" in actions:
					sets.append(Pon(tile))
				if "Chi" in actions:
					sets += [ set for set, t in find_potential_chi(self.hand, tile) ]
				self._set_basic_state()
				self.engine.question_steal(tile, sets)
				self.action = self.action_steal
			else:
				self.server.player_is_ready(self)
		else:
				self.server.player_is_ready(self)


	def round_end(self, player, looser, win_type, payment_name, scores, minipints, diffs):
		self.server.player_is_ready(self)

	def round_end_draw(self, winners, loosers, diffs):
		self.server.player_is_ready(self)

	def round_is_ready(self):
		Player.round_is_ready(self)
		self.engine.set_doras(self.round.doras)
		self.engine.set_round_wind(self.round.round_wind)
		self.engine.set_player_wind(self.wind)

	def stolen_tile(self, player, from_player, action, set, tile):
		Player.stolen_tile(self, player, from_player, action, set, tile)

		if self == player:
			self._set_basic_state()
			self.engine.question_discard()
			self.action = self.action_discard

