from PyQt5.QtGui import QPainter, QPen, QBrush, QImage, QColor, QFont, QPalette
from PyQt5.QtWidgets import *#QWidget, QApplication, QDesktopWidget, QPushButton
from PyQt5.QtCore import Qt, QRectF, QRect, QPoint, QTimer

from game import game_params as gp
import time
import threading

margin=50
window_size=500
n=8 #even integer
CELLRATIO = 3/5
FONTSIZE=10

BLUE = QColor("#031591")
YELLOW = QColor("#ffcc00")
RED = QColor("#ff0000")
BLACK = QColor("#000000")
GREY = QColor("#505050")
WHITE = QColor("#ffffff")

BOARDSIZE = (6,6)

CATFONT = QFont()
CATFONT.setBold(True)
CATFONT.setPointSize(24)
CATPEN = QPen(WHITE)

MONFONT = QFont(CATFONT)
MONFONT.setPointSize(50)
MONPEN = QPen(YELLOW)
TEXTPADDING = 20

QUFONT = QFont()
QUFONT.setPointSize(70)
QUMARGIN = 50

NAMEHEIGHT = 50
NAMEFONT = QFont()
NAMEFONT.setPointSize(20)
SCOREFONT = QFont()
SCOREFONT.setPointSize(50)
SCOREPEN = QPen(WHITE)
HIGHLIGHTPEN = QPen(BLUE)
HIGHLIGHTBRUSH = QBrush(WHITE)

LIGHTPEN = QPen(GREY)
LIGHTBRUSH = QBrush(RED)

BORDERWIDTH = 10
BORDERPEN = QPen(BLACK)
BORDERPEN.setWidth(BORDERWIDTH)
DIVIDERBRUSH = QBrush(WHITE)
DIVIDERWIDTH = 20

FILLBRUSH = QBrush(BLUE)
SCOREHEIGHT = 0.15
ANSWERHEIGHT = 0.15

ANSWERBARS = 30

ANSWERSECS = 5

def updateUI(f):
    def wrapper(self, *args):
        ret = f(self, *args)
        self.update()
        return ret
    return wrapper

class ScoreWidget(QWidget):
    def __init__(self,game,parent=None):
        super().__init__(parent)
        self.game = game

        self.setGeometry(0, parent.height()*(1-SCOREHEIGHT), parent.width(), parent.height()*SCOREHEIGHT)
        colorpal = QPalette()
        colorpal.setColor(QPalette.Background, BLACK)
        self.setPalette(colorpal)

        self.__highlighted_player = None

        self.__light_level = 0
        self.__light_thread = None

        self.show()

    def __lights(self):
        self.__light_level = ANSWERSECS + 1
        while self.__light_level > 0:
            self.__light_level -= 1
            self.update()
            time.sleep(1.)

        self.dehighlight()

    def run_lights(self):
        self.__light_thread = threading.Thread(target = self.__lights, name="lights")
        self.__light_thread.start()

    def paintEvent(self, event):
        h = self.geometry().height()
        w = self.geometry().width()
        qp = QPainter()
        qp.begin(self)
        qp.setBrush(FILLBRUSH)
        qp.drawRect(QRectF(0, DIVIDERWIDTH, w, h))

        qp.setBrush(DIVIDERBRUSH)
        dividerrect = QRectF(0, 0, w, DIVIDERWIDTH)
        qp.drawRect(dividerrect)

        #Light dividers
        num_lights = 9
        light_width = w // num_lights
        light_padding = 3
        ungrouped_rects = [QRect(light_width*i+light_padding, light_padding, light_width - 2*light_padding, DIVIDERWIDTH - 2*light_padding) for i in range(num_lights)]
        grouped_rects = [ [rect for j,rect in enumerate(ungrouped_rects) if abs(num_lights//2 - j)==i] for i in range(5)]
        qp.setBrush(LIGHTBRUSH)
        qp.setPen(LIGHTPEN)
        for i, rects in enumerate(grouped_rects):
            if i < self.__light_level:
                for rect in rects:
                    qp.drawRect(rect)

        margin = 50
        scores = self.game.scores
        sw = w//len(scores)
        for i,(n,s) in enumerate(scores.items()):
            qp.setPen(SCOREPEN)
            qp.setFont(SCOREFONT)
            scorerect = QRectF(sw*i, DIVIDERWIDTH, sw, h-NAMEHEIGHT-DIVIDERWIDTH)
            qp.drawText(scorerect, Qt.TextWordWrap | Qt.AlignVCenter | Qt.AlignHCenter, f'{s:,}')

            namerect = QRectF(sw*i, h-NAMEHEIGHT, sw, NAMEHEIGHT)
            qp.setFont(NAMEFONT)
            if n == self.__highlighted_player:
                qp.setBrush(HIGHLIGHTBRUSH)
                qp.drawRect(namerect)
                qp.setPen(HIGHLIGHTPEN)
            qp.drawText(namerect, Qt.TextWordWrap | Qt.AlignVCenter | Qt.AlignHCenter, n)


    @updateUI
    def highlight(self, name):
        self.run_lights()
        self.__highlighted_player = name

    @updateUI
    def dehighlight(self):
        self.__highlighted_player = None

    @updateUI
    def stop_lights(self):
        self.__light_level = 0
        self.dehighlight()

class BorderWidget(QWidget):
    def __init__(self, game, boardrect, parent=None):
        super().__init__(parent)
        self.game = game
        self.boardrect = boardrect
        self.__answerbarrect = boardrect.adjusted(-ANSWERBARS, 0, ANSWERBARS, 0)
        self.show()
        self.__lit = False

    @property
    def lit(self):
        return self.__lit

    @lit.setter
    def lit(self, val):
        self.__lit = val
        self.update()

    def paintEvent(self, event):
        qp = QPainter()
        qp.begin(self)
        if self.lit:
            qp.setBrush(HIGHLIGHTBRUSH)
            qp.drawRect(self.__answerbarrect)



class BoardWidget(QWidget):
    def __init__(self, game, alex=True, parent=None):
        super().__init__(parent)
        self.game = game
        self.board = game.rounds[0]
        self.alex = alex

        self.responses_open = False

        pheight = parent.geometry().height()
        height = pheight * (1 - SCOREHEIGHT)
        width = height / CELLRATIO
        self.resize(width+BORDERWIDTH, height)

        self.__completed_questions=[]
        # self.__complete=False
        # self.__catlabels = []

        cellheight = self.size().height() // (self.board.size[1]+1)
        self.cellsize = (cellheight/CELLRATIO, cellheight)

        self.show()

    def paintEvent(self, event):
        qp = QPainter()
        qp.begin(self)
        if self.game.active_question is None:
            qp.setBrush(FILLBRUSH)
            parent = self.parent()
            pheight = parent.geometry().height()
            height = pheight * (1 - SCOREHEIGHT)
            width = height / CELLRATIO
            for x in range(self.board.size[0]):
                for y in range(-1,self.board.size[1]):
                    rel_pos = (x*self.cellsize[0] + BORDERWIDTH/2, (y+1)*self.cellsize[1])
                    cell=(x,y)
                    qp.setPen(BORDERPEN)
                    qp.setBrush(FILLBRUSH)
                    cell_rect=QRectF(*rel_pos, *self.cellsize)
                    text_rect = QRectF(cell_rect)
                    text_rect.setX(cell_rect.x()+TEXTPADDING)
                    text_rect.setWidth(cell_rect.width()-2*TEXTPADDING)
                    qp.drawRect(cell_rect)
                    if y==-1:
                        # Categories
                        qp.setPen(CATPEN)
                        qp.setFont(CATFONT)
                        qp.drawText(text_rect, Qt.TextWordWrap | Qt.AlignVCenter | Qt.AlignHCenter, self.board.categories[x])
                    else:
                        # Questions
                        if not self.board.get_question(*cell) in self.game.completed_questions:
                            qp.setPen(MONPEN)
                            qp.setFont(MONFONT)
                            if not self.board.dj:
                                monies = gp.money1
                            else:
                                monies = gp.money2
                            qp.drawText(text_rect, Qt.TextWordWrap | Qt.AlignVCenter | Qt.AlignHCenter, "$"+str(monies[y]))


        else:

            qp.setBrush(FILLBRUSH)
            qp.drawRect(self.rect())
            qp.setPen(CATPEN)
            qp.setFont(QUFONT)

            if self.alex:
                anheight = ANSWERHEIGHT * self.size().height()
                qurect = self.rect().adjusted(QUMARGIN, QUMARGIN, -2*QUMARGIN, - ANSWERHEIGHT * self.size().height())
                anrect = QRectF(QUMARGIN, self.size().height()*(1-ANSWERHEIGHT), self.size().width()-2*QUMARGIN, ANSWERHEIGHT * self.size().height())
                qp.drawText(anrect, Qt.TextWordWrap | Qt.AlignVCenter | Qt.AlignHCenter, self.game.active_question.answer.upper())
                qp.drawLine(0, (1-ANSWERHEIGHT) * self.size().height(), self.size().width(), (1-ANSWERHEIGHT) * self.size().height())

            else:
                qurect = self.rect().adjusted(QUMARGIN, QUMARGIN, -2*QUMARGIN, -2*QUMARGIN)
            qp.drawText(qurect, Qt.TextWordWrap | Qt.AlignVCenter | Qt.AlignHCenter, self.game.active_question.text.upper())


    def load_question(self,i,j):
        q = self.board.get_question(i,j)
        if not q in self.game.completed_questions:
            self.game.active_question = q
            self.game.keystroke_manager.activate('OPEN_RESPONSES')
            self.game.update()

    def mousePressEvent(self, event):
        if not self.game.paused and self.game.active_question is None:
            coord=(event.x()//self.cellsize[0],event.y()//self.cellsize[1]-1)
            if not coord in self.game.completed_questions:
                self.load_question(*coord)


class DisplayWindow(QWidget):
    def __init__(self,game, alex=True, monitor=0):
        super().__init__()
        self.setWindowTitle('Alex')

        colorpal = QPalette()
        colorpal.setColor(QPalette.Background, BLACK)
        self.setPalette(colorpal)

        monitor = QDesktopWidget().screenGeometry(monitor)
        self.move(monitor.left(), monitor.top()) #move to monitor 0
        self.showFullScreen()

        self.boardwidget = BoardWidget(game, alex=alex, parent=self)
        self.boardwidget.move(self.geometry().width()/2 - self.boardwidget.geometry().width()/2, 0)

        self.boardwidget.update()

        self.scoreboard = ScoreWidget(game, parent=self)

        self.borderwidget = BorderWidget(game, self.boardwidget.geometry(), parent=self)
        self.borderwidget.setGeometry(0, 0, self.size().width(), self.boardwidget.size().height())
        self.borderwidget.stackUnder(self.boardwidget)

        self.game = game
        self.game.dc += self
        self.show()


    def update_scores(self, scores):
        self.scoreboard.update_scores(scores)

    def keyPressEvent(self, event):
        self.game.keystroke_manager.call(event.key())