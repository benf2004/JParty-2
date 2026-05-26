

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

var last_buzz = new Date().getTime();

async function buzz() {
    console.log("Buzzer was pressed.")
    if (!$("#buzzer").prop("disabled")) {
        console.log("Buzzer is not disabled.")
        send("BUZZ");
        $("#buzzer").prop("disabled", true);

        setTimeout(function () {
            console.log("Re-enabling buzzer.")
            $("#buzzer").prop("disabled", false);
        }, 250);
    } else {
        console.log("Buzzer IS DISABLED.")
    }
}

var current_page = "";
var disputeCountdownTimer = null;
window.auto_host_enabled = true;
function load_page(pagename) {
    console.log("loading page "+pagename);
    if (!!current_page) {
        console.log("hiding page "+current_page);
        $("."+current_page+"-page").hide();
    }
    try {
        if (pagename !== null && pagename != "null") {
            console.log("showing page "+pagename);
            $("."+pagename+"-page").show();
        }
    } catch {
        console.log("failed");
        return 1;
    }
    current_page = pagename;
    return 0;
}

function setToken(token) {
  var d = new Date();
  d.setTime(d.getTime() + (24*60*60*1000)); // lasts 24 hour
  var expires = "expires="+ d.toUTCString();
  document.cookie = "token=" + token + ";" + expires + ";path=/";
}

function getToken() {
  var name = "token=";
  var decodedCookie = decodeURIComponent(document.cookie);
  var ca = decodedCookie.split(';');
  for(var i = 0; i <ca.length; i++) {
    var c = ca[i];
    while (c.charAt(0) == ' ') {
      c = c.substring(1);
    }
    if (c.indexOf(name) == 0) {
      return c.substring(name.length, c.length);
    }
  }
  return "";
}

function send(msg, text="", buzzerColor, extra={}) {
    var message = {
        message:msg,
        text: text,
        buzzerColor: buzzerColor
    };
    Object.assign(message, extra);
    updater.socket.send(JSON.stringify(message));
}
function wagerForm(form) {
    var scope = form ? $(form) : $(document);
    var amount = scope.find("input[name='wager']").val().replace(/[\s,]/g, '');
    if (amount != "") {
        send("WAGER", amount);
        load_page(null);
    }
    return false;
}
function answerForm(form) {
    var scope = form ? $(form) : $("form.answer_form:visible").first();
    if (!scope.length) {
        scope = $("form.answer_form").first();
    }
    var answer = scope.find("input[name='answer']").val();
    send("ANSWER",answer);
    scope.find("input[name='answer']").val("");
    document.activeElement.blur();
    if (scope.closest("#buzz-answer-panel").length) {
        $("#answer-record-status").text("Judging...");
    } else {
        load_page(null);
    }
    return false;
}

function cluePick(categoryIndex, row) {
    send("CLUE_PICK", categoryIndex + "," + row);
    load_page("buzz");
}

function challengeVote(vote) {
    send("CHALLENGE_VOTE", vote);
    load_page(null);
}

function startGameVote() {
    send("START_GAME_VOTE");
    $("#buzz-status").text("Start vote recorded");
    $("#start-game-button").prop("disabled", true);
}

function playAgainVote() {
    send("PLAY_AGAIN_VOTE");
    $("#buzz-status").text("Play again vote recorded");
    $("#play-again-button").prop("disabled", true);
}

function disputeLastClue() {
    send("DISPUTE_REQUEST");
    $(".dispute-button").prop("disabled", true);
}

function disputeVote(choice) {
    send("DISPUTE_VOTE", choice);
    $("#dispute-status").text("Vote recorded");
    $("#dispute-options button").prop("disabled", true);
}

function setAutoHostControls(payload) {
    payload = payload || {};
    $("#start-game-button").toggle(!!payload.can_start_game).prop("disabled", false);
    $("#play-again-button").toggle(!!payload.can_play_again).prop("disabled", false);
    $(".dispute-button").toggle(!!payload.can_dispute).prop("disabled", false);
}

function setAutoHostState(payload) {
    if (!payload || payload.auto_host_enabled === undefined) {
        return;
    }
    window.auto_host_enabled = !!payload.auto_host_enabled;
    if (!window.auto_host_enabled) {
        $("#display-name-section").hide();
        $("#prompt-button").hide();
        $(".name-hint").text("Sign below to join");
    } else {
        $("#display-name-section").show();
        $("#prompt-button").show();
        $(".name-hint").text("Type your name and sign below");
    }
}

function openDisputeVote(payload) {
    if (disputeCountdownTimer) {
        clearInterval(disputeCountdownTimer);
        disputeCountdownTimer = null;
    }
    $("#dispute-text").text(payload.message || "Vote on the last clue");
    var options = $("#dispute-options");
    options.empty();
    (payload.options || []).forEach(function(option) {
        $("<button>")
            .addClass("jparty-button dispute-option")
            .text(option.label)
            .on("click", function() { disputeVote(option.id); })
            .appendTo(options);
    });
    var secondsRemaining = Number(payload.seconds_remaining || 30);
    function renderDisputeCountdown() {
        $("#dispute-status").text(secondsRemaining + " seconds to vote");
        secondsRemaining -= 1;
        if (secondsRemaining < 0 && disputeCountdownTimer) {
            clearInterval(disputeCountdownTimer);
            disputeCountdownTimer = null;
        }
    }
    renderDisputeCountdown();
    disputeCountdownTimer = setInterval(renderDisputeCountdown, 1000);
    load_page("dispute");
}

function setAutoHostPayload(payload) {
    if (!payload) {
        resetBuzzAnswerPanel();
        return;
    }
    if (payload.categories && payload.clues) {
        renderClueGrid(payload);
    }
    if (payload.max_wager !== undefined) {
        set_max_wager(payload.max_wager);
    }
    if (payload.answer_state === "waiting") {
        showBuzzAnswerWait(payload);
    } else if (payload.answer_state === "ready") {
        showBuzzAnswerReady(payload);
    } else {
        resetBuzzAnswerPanel();
    }
}

function autoHostAutoStartDelay(payload, defaultDelay) {
    if (payload && payload.auto_start_delay_ms !== undefined) {
        return Number(payload.auto_start_delay_ms);
    }
    return defaultDelay;
}

function setAnswerRecordPrompt(payload) {
    var prompt = "Speak now";
    if (payload && payload.prompt) {
        prompt = payload.prompt;
    }
    $("#answer-record-prompt").text(prompt);
    $("#answer-record-status").text("");
}

function resetBuzzAnswerPanel() {
    $("#buzz-answer-panel").hide().removeClass("waiting ready");
    $("#buzz-answer-controls").show();
    $("#answer-record-status").removeClass("active").text("");
    $("#answer-record-prompt").text("Record your answer");
}

function showBuzzAnswerWait(payload) {
    setAnswerRecordPrompt(payload || {prompt: "Wait to talk..."});
    $("#buzz-answer-panel").show().removeClass("ready").addClass("waiting");
}

function showBuzzAnswerReady(payload) {
    setAnswerRecordPrompt(payload);
    $("#buzz-answer-panel").show().removeClass("waiting").addClass("ready");
    $("#buzz-answer-controls").show();
}

function autoHostStatus(purpose) {
    if (purpose === "answer") {
        return $("#answer-record-status");
    }
    if (purpose === "daily_double_wager") {
        return $("#dd-wager-status");
    }
    return $("#recording-status");
}

function renderClueGrid(payload) {
    var grid = $("#clue-grid");
    grid.empty();
    payload.categories.forEach(function(category, categoryIndex) {
        grid.append($("<div>").addClass("clue-category").text(category));
    });
    payload.clues.forEach(function(clue) {
        var button = $("<button>")
            .addClass("clue-button")
            .text(clue.complete ? "" : "$" + clue.value)
            .prop("disabled", clue.complete)
            .on("click", function() {
                cluePick(clue.category_index, clue.row);
            });
        grid.append(button);
    });
}

function supportedAudioType() {
    var types = [
        "audio/webm;codecs=opus",
        "audio/ogg;codecs=opus",
        "audio/mp4",
        "audio/webm"
    ];
    if (!window.MediaRecorder) {
        return "";
    }
    for (var i = 0; i < types.length; i++) {
        if (MediaRecorder.isTypeSupported(types[i])) {
            return types[i];
        }
    }
    return "";
}

async function recordAutoHostAudio(purpose) {
    if (!navigator.mediaDevices || !window.MediaRecorder) {
        alert("Microphone recording is not available in this browser context. Use the HTTPS buzzer URL, accept/trust the local JParty certificate if prompted, or use the on-screen fallback.");
        return;
    }

    var status = autoHostStatus(purpose);
    status.addClass("active");
    status.text("Speak now");
    try {
        var stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        var mimeType = supportedAudioType();
        var options = mimeType ? { mimeType: mimeType } : {};
        var recorder = new MediaRecorder(stream, options);
        var chunks = [];
        recorder.ondataavailable = function(event) {
            if (event.data && event.data.size > 0) {
                chunks.push(event.data);
            }
        };
        recorder.onstop = async function() {
            stream.getTracks().forEach(function(track) { track.stop(); });
            status.removeClass("active");
            status.text("Sending...");
            var blob = new Blob(chunks, { type: recorder.mimeType || mimeType || "audio/webm" });
            await uploadAutoHostAudio(purpose, blob);
        };
        recorder.start();
        setTimeout(function() {
            if (recorder.state === "recording") {
                recorder.stop();
            }
        }, purpose === "answer" ? 4500 : (purpose === "daily_double_wager" ? 4500 : 3500));
    } catch (err) {
        console.log(err);
        status.removeClass("active");
        status.text("");
        alert("Could not access the microphone. Allow mic permission for the HTTPS JParty page, or use the on-screen fallback.");
    }
}

async function uploadAutoHostAudio(purpose, blob) {
    var status = autoHostStatus(purpose);
    status.text("Sending...");
    var form = new FormData();
    form.append("token", getToken());
    form.append("purpose", purpose);
    form.append("sequence_id", String(new Date().getTime()));
    form.append("audio", blob, "auto-host-audio.webm");
    try {
        var response = await fetch("/api/player-audio", { method: "POST", body: form });
        if (!response.ok) {
            throw new Error("Upload failed");
        }
        if (purpose === "answer") {
            status.text("Judging...");
        } else if (purpose === "clue_selection") {
            status.text("Finding clue...");
        } else if (purpose === "daily_double_wager") {
            status.text("Reading wager...");
        } else {
            status.text("Sent");
        }
    } catch (err) {
        console.log(err);
        status.text("");
        alert("Could not send audio. Please use the on-screen fallback.");
    }
}

function nameForm(name, buzzerColor, displayName="") {
    console.log(name);
    send("NAME", name, buzzerColor, {displayName: displayName});
}

function set_max_wager(score) {
    $(".wager_input").attr("max", Math.max(0, score));
    $(".wager_input").attr("min",0);
    console.log("Max wager:" + $(".wager_input").attr("max"));
}

const padding = 2;
const canvasratio = 1.3422;

var signaturePad;

function resizeCanvas() {
    const ratio =  Math.max(window.devicePixelRatio || 1, 1);
    const canvas = document.querySelector("canvas");
    canvas.width = canvas.offsetWidth * ratio;
    canvas.height = canvas.width / canvasratio;
    canvas.getContext("2d").scale(ratio, ratio);
    signaturePad.clear(); // otherwise isEmpty() might return incorrect value
}


$(document).ready(function() {
    if (!window.console) window.console = {};
    if (!window.console.log) window.console.log = function() {};

    updater.start();

    const canvas = document.querySelector("canvas");
    canvas.style.width = "100%";

    var bgColor = "#1010a1";
    if (window.jparty_theme && window.jparty_theme.nameLabelColor) {
        bgColor = window.jparty_theme.nameLabelColor;
    }
    signaturePad = new SignaturePad(canvas, {
        penColor: "#ffffff",
        backgroundColor: bgColor
    });


    window.addEventListener("resize", resizeCanvas);
    // resizeCanvas();

    var cookie = getToken();
    if (cookie != "") {
        console.log("checking token "+cookie)
        updater.socket.onopen = function (event) {
            updater.socket.send(JSON.stringify({message:"CHECK_IF_EXISTS", text:cookie}));
        };
    } else {
        console.log("no cookie")
        load_page("name");
        resizeCanvas();
    };


    $("#clear-button").on("click", function () {
        signaturePad.clear()
    });

    $("#undo-button").on("click", function () {
        const data = signaturePad.toData();

        if (data) {
            data.pop(); // remove the last dot or line
            signaturePad.fromData(data);
        }
    });

    $("#prompt-button").on("click", function () {
        let name = prompt("Enter name", "");
        if (name != null) {
            nameForm(name);
        };
    });

    $("#submit-button").on("click", function () {
        if (!signaturePad.isEmpty() && $("#buzzers").find(":selected").val() != "") {
            let buzzerColor = $("#buzzers").find(":selected").val()
            console.log("Selected buzzer color: " + buzzerColor)
            $("#buzzer").css("background-color", buzzerColor)
            let displayName = "";
            if (window.auto_host_enabled) {
                displayName = $("input[name='displayname']").val().trim();
                if (displayName == "") {
                    alert("Please type your name too");
                    return;
                }
            }
            let image = signaturePad.toDataURL();
            console.log(image);
            nameForm(image, buzzerColor, displayName);
        }
        else {
            alert("Please make sure you signed your name and selected a buzzer")
        };
    });
});





var updater = {
    socket: null,

    start: function() {
        var socketScheme = location.protocol === "https:" ? "wss://" : "ws://";
        var url = socketScheme + location.host + "/buzzersocket";
        updater.socket = new WebSocket(url);
        updater.socket.onclose = function(event) { location.reload(true); };
        updater.socket.onmessage = function(event) {
            jsondata = JSON.parse(event.data);
            switch (jsondata.message) {
                case "GAMEFULL":
                    alert("Game has too many players!")
                    window.location.reload()
                    break;
                case "GAMESTARTED":
                    alert("Game has started!")
                    break;
                case "TOKEN":
                    load_page("buzz");
                    setToken(jsondata.text);
                    break;
                case "NEW":
                    var state = {};
                    try {
                        state = JSON.parse(jsondata.text || "{}");
                    } catch (err) {
                        console.log(err);
                    }
                    setAutoHostState(state);
                    load_page("name");
                    resizeCanvas();
                    break;
                case "EXISTS":
                    console.log("Already exists" + jsondata.text);
                    state = JSON.parse(jsondata.text);
                    setAutoHostState(state);
                    set_max_wager(state.score);
                    setAutoHostPayload(state.auto_payload);
                    load_page(state.page);
                    break;
                case "PROMPTWAGER":
                    set_max_wager(jsondata.text);
                    load_page("wager");
                    break;
                case "PROMPTANSWER":
                    $(".answer-page input[name='answer']").val("");
                    load_page("answer");
                    break;
                case "TOOLATE":
                    if (current_page === "answer") {
                        answerForm($(".answer-page form.answer_form").first());
                    }
                    break;
                case "PROMPT_SELECT_CLUE":
                    var selectPayload = JSON.parse(jsondata.text);
                    setAutoHostPayload(selectPayload);
                    $("#recording-status").text("");
                    load_page("select");
                    setTimeout(function() { recordAutoHostAudio("clue_selection"); }, autoHostAutoStartDelay(selectPayload, 800));
                    break;
                case "PROMPT_RECORD_ANSWER":
                    showBuzzAnswerReady(JSON.parse(jsondata.text || "{}"));
                    load_page("buzz");
                    break;
                case "PROMPT_DD_WAGER":
                    set_max_wager(jsondata.text);
                    $("#dd-wager-status").text("");
                    load_page("dd_wager");
                    break;
                case "PROMPT_BUZZ":
                    resetBuzzAnswerPanel();
                    load_page("buzz");
                    break;
                case "AUTO_HOST_CONTROLS":
                    setAutoHostControls(JSON.parse(jsondata.text || "{}"));
                    break;
                case "PROMPT_START_GAME":
                    setAutoHostControls({can_start_game: true});
                    load_page("buzz");
                    break;
                case "PROMPT_PLAY_AGAIN":
                    setAutoHostControls({can_play_again: true});
                    load_page("buzz");
                    break;
                case "DISPUTE_OPEN":
                    openDisputeVote(JSON.parse(jsondata.text || "{}"));
                    break;
                case "DISPUTE_RESULT":
                    if (disputeCountdownTimer) {
                        clearInterval(disputeCountdownTimer);
                        disputeCountdownTimer = null;
                    }
                    $("#dispute-status").text(jsondata.text);
                    setTimeout(function() { load_page("buzz"); }, 1800);
                    break;
                case "DISPUTE_VOTE_RECORDED":
                    $("#dispute-status").text(jsondata.text);
                    break;
                case "JUDGEMENT_RESULT":
                    var judgement = JSON.parse(jsondata.text);
                    $("#judgement-text").text(judgement.verdict.toUpperCase());
                    $("#judgement-reason").text(judgement.transcript);
                    resetBuzzAnswerPanel();
                    load_page("judgement");
                    setTimeout(function() {
                        if (current_page === "judgement") {
                            load_page("buzz");
                        }
                    }, 1800);
                    break;
                case "PROMPT_WAIT_ANSWER":
                    showBuzzAnswerWait(JSON.parse(jsondata.text || "{}"));
                    load_page("buzz");
                    break;
                case "PROMPT_RECORD_ANSWER_AUTO":
                    showBuzzAnswerReady(JSON.parse(jsondata.text || "{}"));
                    load_page("buzz");
                    setTimeout(function() { recordAutoHostAudio("answer"); }, 300);
                    break;
                case "CHALLENGE_OPEN":
                    var challenge = JSON.parse(jsondata.text);
                    $("#challenge-text").text(challenge.answering_player + " challenged. Vote:");
                    load_page("challenge");
                    break;
                case "CHALLENGE_RESULT":
                    load_page("buzz");
                    break;
                case "AUTO_HOST_FALLBACK":
                    if (current_page === "select") {
                        $("#recording-status").removeClass("active").text(jsondata.text);
                    } else if (current_page === "dd_wager") {
                        $("#dd-wager-status").removeClass("active").text(jsondata.text);
                    } else if ($("#buzz-answer-panel").is(":visible")) {
                        $("#answer-record-status").removeClass("active").text(jsondata.text);
                    } else {
                        console.log(jsondata.text);
                    }
                    break;
            }
        }
    }
};
