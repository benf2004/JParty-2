"""Team state and game integration; participants remain individual connections."""
from dataclasses import dataclass, field
import base64
import json
import struct
import uuid
from jparty.constants import MAXPLAYERS, MAXTEAMPLAYERS


@dataclass(eq=False)
class Team:
    id: str
    name: str
    members: list = field(default_factory=list)
    representative: object = None
    score: int = 0
    wager: object = None
    finalanswer: str = ""
    final_eligible: bool = True
    signature: str = ""


def member_name(player):
    if player is None:
        return "Nobody"
    return player.display_name or ("Player" if player.name.startswith("data:image") else player.name)


class TeamMode:
    """Methods run on the Qt game thread, including queued socket roster actions."""

    def init_teams(self):
        self.team_mode = bool(getattr(self, 'config', {}).get('team_mode', False))
        self.teams = []
        self.roster_version = 0

    def scoring_contestant(self, player):
        return getattr(player, "team", None) or player

    def contestants(self):
        if getattr(self, "team_mode", False):
            return [team for team in self.teams if team.members]
        return self.players

    def final_players(self):
        if getattr(self, "team_mode", False):
            return [t.representative for t in self.contestants()
                    if t.final_eligible and t.representative is not None]
        return self.players

    def representative(self, contestant):
        return contestant.representative if isinstance(contestant, Team) else contestant

    def teams_ready(self):
        if not getattr(self, "team_mode", False):
            return len(getattr(self, "players", [])) <= MAXPLAYERS
        return (len(self.players) <= MAXTEAMPLAYERS and len(self.contestants()) >= 2
                and all(getattr(p, "team", None) in self.teams for p in self.players))

    def team_state(self, player=None):
        team = getattr(player, "team", None)
        return {
            "team_mode": getattr(self, "team_mode", False),
            "teams": [{"id": t.id, "name": t.name, "members": len(t.members)}
                      for t in getattr(self, "teams", [])],
            "joined": player is not None,
            "team_id": team.id if team else None,
            "team_name": team.name if team else "",
            "representative": member_name(team.representative) if team else "",
            "is_representative": bool(team and team.representative is player),
            "score": player.score if player else 0,
            "in_lobby": self.current_round is None,
            "can_create_team": self.current_round is None and len(self.teams) < 8,
        }

    def broadcast_teams(self):
        controller = getattr(self, "buzzer_controller", None)
        if controller:
            for socket in tuple(getattr(controller, "sockets", set())):
                if socket.player is None:
                    socket.send("TEAM_STATE", json.dumps(self.team_state()))
            for player in controller.connected_players:
                if player.waiter and getattr(player, "connected", True):
                    player.waiter.send("TEAM_STATE", json.dumps(self.team_state(player)))
        if getattr(self, "dc", None):
            self.dc.scoreboard.refresh_players()
        self.teams_changed.emit()

    def roster_changed(self):
        self.roster_version = getattr(self, "roster_version", 0) + 1
        self.cancel_start_game("Start cancelled: teams changed")
        self.broadcast_teams()
        if getattr(self, "host_display", None):
            self.host_display.welcome_widget.check_start()

    def configure_teams(self, enabled, names=None):
        if self.current_round is not None:
            return False
        if names is None:
            for player in self.players:
                player.team = None
            self.teams = []
            self.team_mode = bool(enabled)
            self.roster_changed()
            return True
        if not 2 <= len(names) <= 8:
            return False
        names = [str(name).strip()[:40] for name in names]
        if any(not name for name in names) or len(set(names)) != len(names):
            return False
        if not enabled and len(self.players) > MAXPLAYERS:
            return False
        old = {t.id: t for t in self.teams}
        self.teams = [old.get(f"team-{i+1}", Team(f"team-{i+1}", name))
                      for i, name in enumerate(names)]
        for team, name in zip(self.teams, names):
            team.name = name
        self.team_mode = bool(enabled)
        for player in self.players:
            if not enabled or player.team not in self.teams:
                if player.team:
                    old_team = player.team
                    old_team.members.remove(player)
                    if old_team.representative is player:
                        old_team.representative = next(iter(old_team.members), None)
                player.team = None
        self.roster_changed()
        return True

    def make_team(self, details):
        """Validate a proposed team without changing the roster until join succeeds."""
        if not self.team_mode or self.current_round is not None:
            raise ValueError('Teams can only be created in the lobby.')
        if len(self.teams) >= 8:
            raise ValueError('Eight teams have already been created. Choose an existing team.')
        if not isinstance(details, dict):
            raise ValueError('Type and draw a team name before creating your team.')
        name, signature = details.get('name'), details.get('signature')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
            raise ValueError('Enter a team name between 1 and 40 characters.')
        name = name.strip()
        if any(t.name.casefold() == name.casefold() for t in self.teams):
            raise ValueError('That team already exists. Choose it from the list or use a different name.')
        if not isinstance(signature, str) or not signature.startswith('data:image/png;base64,') or len(signature) > 350000:
            raise ValueError('Draw your team name before creating your team.')
        try:
            image = base64.b64decode(signature[22:], validate=True)
            if image[:16] != b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR':
                raise ValueError()
            width, height = struct.unpack('>II', image[16:24])
            if not (0 < width <= 2048 and 0 < height <= 2048 and width * height <= 2097152):
                raise ValueError()
            from PyQt6.QtGui import QImage
            if QImage.fromData(image, 'PNG').isNull():
                raise ValueError()
        except (ValueError, struct.error):
            raise ValueError('The team drawing could not be read. Clear it and sign again.') from None
        return Team('team-' + uuid.uuid4().hex, name, signature=signature)

    def assign_team(self, player, team_id):
        if (self.current_round is not None or not self.team_mode
                or player not in self.players):
            return False
        team = next((t for t in self.teams if t.id == team_id), None)
        if team is None:
            return False
        old = player.team
        if old is team:
            return True
        if old:
            old.members.remove(player)
            if old.representative is player:
                old.representative = next(iter(old.members), None)
            if not old.members:
                self.teams.remove(old)
        player.team = team
        team.members.append(player)
        if team.representative is None:
            team.representative = player
        if self.auto_host.player_in_control is player:
            self.set_player_in_control(team.representative)
        self.roster_changed()
        return True

    def can_remove_team_member(self, player):
        # A clue being judged retains its answering identity. Recover team
        # decision controls freely, but finish that response before removal.
        return (player is not self.answering_player
                and not getattr(self, "_Game__sorted_players", None))

    def transfer_representative(self, player):
        team = getattr(player, "team", None)
        if not self.team_mode or team is None or player not in self.players:
            return
        old = team.representative
        if old is player:
            return
        team.representative = player
        if old:
            sorted_players = getattr(self, "_Game__sorted_players", None)
            if sorted_players and old in sorted_players:
                sorted_players[sorted_players.index(old)] = player
            page, payload = old.page, old.auto_payload
            old.page, old.auto_payload = "buzz", {}
            if old.waiter:
                old.waiter.send("PROMPT_BUZZ")
            if page in ("select", "dd_wager", "wager", "answer"):
                player.page, player.auto_payload = page, payload
                if page == "select":
                    player.waiter.send("PROMPT_SELECT_CLUE", json.dumps(payload))
                elif page == "dd_wager":
                    player.waiter.send("PROMPT_DD_WAGER", str(payload.get("max_wager", 0)))
                elif page == "wager":
                    player.waiter.send("PROMPTWAGER", str(max(team.score, 0)))
                else:
                    player.waiter.send("PROMPTANSWER")
        if self.auto_host.player_in_control is old:
            self.set_player_in_control(player)
        if self.answering_player is old and (getattr(self.current_round, "question", None)
                                               or (self.active_question and self.active_question.dd)):
            self.answering_player = player
        if self.current_round is None:
            self.roster_changed()
        else:
            self.broadcast_teams()

    def handle_team_action(self, action):
        kind, *args = action
        if kind == "join":
            handler, name, color, display_name, team_id, *creation = args
            new_team = creation[0] if creation else None
            if handler.player is not None or getattr(handler, "ws_connection", True) is None:
                return
            if not self.buzzer_controller.accepting_players or self.current_round is not None:
                handler.send("GAMESTARTED")
                return
            if len(self.players) >= (MAXTEAMPLAYERS if self.team_mode else MAXPLAYERS):
                handler.send("FULL")
                return
            if not isinstance(name, str) or not name.strip() or len(name) > 350000:
                handler.send('TEAM_ERROR', 'Enter your name and signature before joining.')
                return
            if self.team_mode and (not isinstance(display_name, str) or not 1 <= len(display_name.strip()) <= 40):
                handler.send('TEAM_ERROR', 'Enter your individual name (up to 40 characters).')
                return
            team = next((t for t in self.teams if t.id == team_id), None)
            if self.team_mode and new_team is not None:
                try:
                    if team_id:
                        raise ValueError('Choose an existing team or create a new one, not both.')
                    team = self.make_team(new_team)
                except ValueError as error:
                    handler.send('TEAM_ERROR', str(error))
                    return
            if self.team_mode and team is None:
                handler.send("TEAM_ERROR", "Choose a team before joining.")
                handler.send("TEAM_STATE", json.dumps(self.team_state()))
                return
            from jparty.game import Player
            player = Player(name, color, handler, display_name.strip() if isinstance(display_name, str) else '')
            handler.player = player
            self.buzzer_controller.connected_players.append(player)
            self.players = self.buzzer_controller.connected_players
            if self.team_mode:
                if new_team is not None:
                    self.teams.append(team)
                self.assign_team(player, team.id)
            self.new_player()
            handler.send("TOKEN", player.token.hex())
            handler.send("TEAM_STATE", json.dumps(self.team_state(player)))
            self.publish_start_countdown()
        elif kind == "change":
            player, team_id = args
            if not self.assign_team(player, team_id) and player and player.waiter:
                player.waiter.send("TEAM_ERROR", "Teams can only be changed in the lobby.")
        elif kind == "refresh":
            self.broadcast_teams()
        elif kind in ("answer", "buzz", "wager", "select_clue"):
            getattr(self.buzzer_controller, kind)(*args, queued=True)

    def reset_teams(self):
        for team in getattr(self, "teams", []):
            team.members.clear()
            team.representative = None
            team.score, team.wager, team.finalanswer = 0, None, ""
            team.final_eligible = True
        self.roster_version = getattr(self, "roster_version", 0) + 1
