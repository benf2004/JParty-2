

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

function send(msg, text="", buzzerColor) {
    var message = {
        message:msg,
        text: text,
        buzzerColor: buzzerColor
    };
    updater.socket.send(JSON.stringify(message));
}
function wagerForm() {
    var amount =$("input[name='wager']").val().replace(/[\s,]/g, '');
    if (amount != "") {
        send("WAGER", amount);
        load_page(null);
    }
    return false;
}
function answerForm() {
    var answer = $("input[name='answer']").val();
    send("ANSWER",answer);
    document.activeElement.blur();
    load_page(null);
    return false;
}

function cluePick(categoryIndex, row) {
    send("CLUE_PICK", categoryIndex + "," + row);
    load_page(null);
}

function requestChallenge() {
    send("CHALLENGE_REQUEST");
    $("#judgement-text").text("Challenge requested");
}

function acceptJudgement() {
    send("JUDGEMENT_ACCEPT");
    load_page(null);
}

function challengeVote(vote) {
    send("CHALLENGE_VOTE", vote);
    load_page(null);
}

function setAutoHostPayload(payload) {
    if (!payload) {
        return;
    }
    if (payload.categories && payload.clues) {
        renderClueGrid(payload);
    }
    if (payload.max_wager !== undefined) {
        set_max_wager(payload.max_wager);
    }
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
        alert("Microphone recording is not available. Please use the on-screen fallback.");
        return;
    }

    var status = $("#recording-status");
    status.text("Recording...");
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
            var blob = new Blob(chunks, { type: recorder.mimeType || mimeType || "audio/webm" });
            await uploadAutoHostAudio(purpose, blob);
        };
        recorder.start();
        setTimeout(function() {
            if (recorder.state === "recording") {
                recorder.stop();
            }
        }, purpose === "answer" ? 5500 : 3500);
    } catch (err) {
        console.log(err);
        status.text("");
        alert("Could not access the microphone. Please use the on-screen fallback.");
    }
}

async function uploadAutoHostAudio(purpose, blob) {
    var status = $("#recording-status");
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
        status.text("Sent");
    } catch (err) {
        console.log(err);
        status.text("");
        alert("Could not send audio. Please use the on-screen fallback.");
    }
}

function nameForm(name, buzzerColor) {
    console.log(name);
    send("NAME",name, buzzerColor);
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
            let image = signaturePad.toDataURL();
            console.log(image);
            nameForm(image, buzzerColor);
        }
        else {
            alert("Please make sure you signed your name and selected a buzzer")
        };
    });
});





var updater = {
    socket: null,

    start: function() {
        var url = "ws://" + location.host + "/buzzersocket";
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
                    load_page("name");
                    resizeCanvas();
                    break;
                case "EXISTS":
                    console.log("Already exists" + jsondata.text);
                    state = JSON.parse(jsondata.text);
                    set_max_wager(state.score);
                    setAutoHostPayload(state.auto_payload);
                    load_page(state.page);
                    break;
                case "PROMPTWAGER":
                    set_max_wager(jsondata.text);
                    load_page("wager");
                    break;
                case "PROMPTANSWER":
                    load_page("answer");
                    break;
                case "TOOLATE":
                    answerForm();
                    break;
                case "PROMPT_SELECT_CLUE":
                    setAutoHostPayload(JSON.parse(jsondata.text));
                    load_page("select");
                    break;
                case "PROMPT_RECORD_ANSWER":
                    load_page("record_answer");
                    break;
                case "PROMPT_DD_WAGER":
                    set_max_wager(jsondata.text);
                    load_page("dd_wager");
                    break;
                case "JUDGEMENT_RESULT":
                    var judgement = JSON.parse(jsondata.text);
                    $("#judgement-text").text(judgement.verdict.toUpperCase());
                    $("#judgement-reason").text(judgement.reason + " " + judgement.transcript);
                    load_page("judgement");
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
                    alert(jsondata.text);
                    break;
            }
        }
    }
};



