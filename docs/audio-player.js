/* ============================================================
   ACIM Daily Minute — Shared Audio Player
   Usage: initAudioPlayer('#container', 'path/to/audio.mp3')
          initAudioPlayer(element, url, { blue: true })
   ============================================================ */

var PLAY_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.2v13.6c0 .7.8 1.1 1.4.7l10.2-6.8c.6-.4.6-1.2 0-1.6L9.4 4.5c-.6-.4-1.4 0-1.4.7z"/></svg>';
var PAUSE_ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>';

var acimPlayers = [];

function pauseOtherPlayers(except) {
    acimPlayers.forEach(function (p) {
        if (p !== except) p.pause();
    });
}

function initAudioPlayer(containerSelector, audioSrc, options) {
    var container = typeof containerSelector === 'string'
        ? document.querySelector(containerSelector)
        : containerSelector;
    if (!container) return null;

    if (container._acimPlayer && container._acimPlayer.destroy) {
        container._acimPlayer.destroy();
    }

    container.classList.add('audio-player');
    container.classList.remove('audio-player--error', 'audio-player--loading');
    container.innerHTML = '';

    var blue = (options && options.blue) || false;
    if (blue) container.classList.add('audio-player--blue');

    if (!audioSrc) {
        container.classList.add('audio-player--error');
        var missing = document.createElement('span');
        missing.className = 'audio-player__message';
        missing.textContent = 'Audio coming soon';
        container.appendChild(missing);
        return null;
    }

    var audio = document.createElement('audio');
    audio.preload = 'metadata';
    audio.src = audioSrc;

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'audio-player__btn';
    btn.setAttribute('aria-label', 'Play');
    btn.innerHTML = PLAY_ICON;

    var progress = document.createElement('input');
    progress.type = 'range';
    progress.className = 'audio-player__progress';
    progress.min = '0';
    progress.max = '100';
    progress.value = '0';
    progress.step = '0.1';
    progress.setAttribute('aria-label', 'Seek');

    var time = document.createElement('span');
    time.className = 'audio-player__time';
    time.textContent = '0:00 / 0:00';

    container.appendChild(btn);
    container.appendChild(progress);
    container.appendChild(time);
    container.appendChild(audio);

    var playing = false;

    function formatTime(s) {
        if (isNaN(s) || !isFinite(s)) return '0:00';
        var m = Math.floor(s / 60);
        var sec = Math.floor(s % 60);
        return m + ':' + (sec < 10 ? '0' : '') + sec;
    }

    function updateTime() {
        time.textContent = formatTime(audio.currentTime) + ' / ' + formatTime(audio.duration);
        if (audio.duration) {
            progress.value = (audio.currentTime / audio.duration * 100).toString();
        }
    }

    function pause() {
        audio.pause();
    }

    function destroy() {
        audio.pause();
        audio.removeAttribute('src');
        audio.load();
        var idx = acimPlayers.indexOf(api);
        if (idx !== -1) acimPlayers.splice(idx, 1);
        container.innerHTML = '';
        container._acimPlayer = null;
    }

    btn.addEventListener('click', function () {
        if (playing) {
            audio.pause();
            return;
        }
        pauseOtherPlayers(api);
        container.classList.add('audio-player--loading');
        var p = audio.play();
        if (p && p.catch) {
            p.catch(function () {
                container.classList.remove('audio-player--loading');
            });
        }
    });

    audio.addEventListener('play', function () {
        playing = true;
        btn.innerHTML = PAUSE_ICON;
        btn.setAttribute('aria-label', 'Pause');
        container.classList.remove('audio-player--loading');
    });

    audio.addEventListener('pause', function () {
        playing = false;
        btn.innerHTML = PLAY_ICON;
        btn.setAttribute('aria-label', 'Play');
    });

    audio.addEventListener('ended', function () {
        playing = false;
        btn.innerHTML = PLAY_ICON;
        btn.setAttribute('aria-label', 'Play');
        progress.value = '0';
    });

    audio.addEventListener('timeupdate', updateTime);

    audio.addEventListener('loadedmetadata', function () {
        time.textContent = '0:00 / ' + formatTime(audio.duration);
    });

    progress.addEventListener('input', function () {
        if (audio.duration) {
            audio.currentTime = (progress.value / 100) * audio.duration;
        }
    });

    audio.addEventListener('error', function () {
        audio.removeAttribute('src');
        container.innerHTML = '';
        container.classList.add('audio-player--error');
        var msg = document.createElement('span');
        msg.className = 'audio-player__message';
        msg.textContent = 'Audio coming soon';
        container.appendChild(msg);
    });

    var api = {
        play: function () {
            pauseOtherPlayers(api);
            return audio.play();
        },
        pause: pause,
        destroy: destroy
    };

    acimPlayers.push(api);
    container._acimPlayer = api;
    return api;
}
