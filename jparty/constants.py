FJTIME = 31
QUESTIONTIME = 4
MONIES = [[200, 400, 600, 800, 1000], [400, 800, 1200, 1600, 2000]]
MAXPLAYERS = 8
PORT = 8080
HTTPS_PORT = 8443
VIDEO_PORT = 8081
DESIGNER_URL = "https://benf2004.github.io/JParty-2/designer_site/game/"
VIDEO_PLAY_TIME = 10
BEFORE_REVEAL_WAIT_TIME = 1
CATEGORY_REVEAL_TIME = 2
QUESTION_REVEAL_TIME = 0.4
BUZZER_DELAY = 0.25 # in s


DEFAULT_CONFIG = {
  'theme': 'Default',
  'showtextwithimages': 'Show both',
  'earlybuzztimeout': 10,
  'allownegative': 'True',
  'allownegativeinfinal': 'True',
  'use_wayback_first': True,
  'mute_sound': False,
  'auto_host': {
    'enabled': False,
    'ai_provider': 'openai',
    'openai_api_key': '',
    'tts_voice': 'coral',
    'local_llm_base_url': 'http://localhost:11434/v1',
    'local_llm_model': 'qwen2.5:7b',
    'local_stt_base_url': 'http://localhost:8082/v1',
    'local_stt_model': 'whisper',
    'local_tts_base_url': 'http://localhost:8880/v1',
    'local_tts_model': 'kokoro',
    'local_tts_voice': 'af_heart',
    'selection_mode': 'voice_with_gui_fallback',
    'answer_judging': 'auto_with_challenge',
    'leniency': 'normal',
    'auto_judge_confidence': 0.82,
    'host_review_confidence': 0.55,
  },
}
