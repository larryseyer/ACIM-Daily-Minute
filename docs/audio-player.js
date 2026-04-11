/* ============================================================
   ACIM Daily Minute — Shared Audio Player Component
   Custom UI wrapping HTML5 <audio> element.
   Usage: initAudioPlayer('#container-id', 'path/to/audio.mp3')
   ============================================================ */

function initAudioPlayer(containerSelector, audioSrc, options) {
    var container = document.querySelector(containerSelector);
    if (!container) return null;

    var blue = (options && options.blue) || false;
    if (blue) container.classList.add('audio-player--blue');

    var audio = document.createElement('audio');
    audio.preload = 'metadata';
    if (audioSrc) audio.src = audioSrc;

    // Build UI
    var btn = document.createElement('button');
    btn.className = 'audio-player__btn';
    btn.setAttribute('aria-label', 'Play');
    btn.textContent = '\u25B6';

    var progress = document.createElement('input');
    progress.type = 'range';
    progress.className = 'audio-player__progress';
    progress.min = '0';
    progress.max = '100';
    progress.value = '0';
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

    btn.addEventListener('click', function () {
        if (playing) {
            audio.pause();
        } else {
            container.classList.add('audio-player--loading');
            var p = audio.play();
            if (p && p.catch) {
                p.catch(function () {
                    container.classList.remove('audio-player--loading');
                });
            }
        }
    });

    audio.addEventListener('play', function () {
        playing = true;
        btn.textContent = '\u275A\u275A';
        btn.setAttribute('aria-label', 'Pause');
        container.classList.remove('audio-player--loading');
    });

    audio.addEventListener('pause', function () {
        playing = false;
        btn.textContent = '\u25B6';
        btn.setAttribute('aria-label', 'Play');
    });

    audio.addEventListener('ended', function () {
        playing = false;
        btn.textContent = '\u25B6';
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

    // Handle missing audio gracefully
    audio.addEventListener('error', function () {
        container.innerHTML = '';
        container.classList.add('audio-player--error');
        var msg = document.createElement('span');
        msg.className = 'audio-player__message';
        msg.textContent = 'Audio coming soon';
        container.appendChild(msg);
    });

    return {
        play: function () { audio.play(); },
        pause: function () { audio.pause(); },
        destroy: function () {
            audio.pause();
            audio.src = '';
            container.innerHTML = '';
        }
    };
}
