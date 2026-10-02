/**
 * Main Application Logic for Tamagotchi Girlfriend TWA
 * Integrates Telegram WebApp SDK, Sliders, Tags, 3D Avatar Moods, and Realtime Reactions
 */

document.addEventListener('DOMContentLoaded', () => {
    // -------------------------------------------------------------
    // 1. Telegram WebApp SDK Setup
    // -------------------------------------------------------------
    const tg = window.Telegram?.WebApp;
    if (tg) {
        tg.ready();
        tg.expand();
        try {
            tg.setHeaderColor('#FFF5F7');
            tg.setBackgroundColor('#FFF5F7');
        } catch (e) {
            console.log('TG header customization not supported');
        }
    }

    // Haptic feedback helper
    const haptic = (type = 'medium') => {
        if (!tg || !tg.HapticFeedback) return;
        try {
            if (['light', 'medium', 'heavy', 'rigid', 'soft'].includes(type)) {
                tg.HapticFeedback.impactOccurred(type);
            } else if (['error', 'success', 'warning'].includes(type)) {
                tg.HapticFeedback.notificationOccurred(type);
            }
        } catch (e) {
            console.warn('Haptic feedback error:', e);
        }
    };

    // Synthesized cute chime audio (no external mp3 files required)
    const playCuteChime = () => {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const now = ctx.currentTime;
            
            // Major triad chords (C6, E6, G6)
            [1046.50, 1318.51, 1567.98].forEach((freq, i) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sine';
                osc.frequency.setValueAtTime(freq, now + i * 0.1);
                gain.gain.setValueAtTime(0.15, now + i * 0.1);
                gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.1 + 0.6);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(now + i * 0.1);
                osc.stop(now + i * 0.1 + 0.65);
            });
        } catch (e) {
            console.log('WebAudio not allowed yet:', e);
        }
    };

    // -------------------------------------------------------------
    // 2. Initialize 3D Avatar Viewer
    // -------------------------------------------------------------
    let viewer = null;
    try {
        viewer = new GirlAvatarViewer('avatar-container');
    } catch (err) {
        console.error('Error initializing 3D viewer:', err);
    }

    // -------------------------------------------------------------
    // 3. Elements & State
    // -------------------------------------------------------------
    // Tamagotchi Live Gauges Elements
    const barHunger = document.getElementById('bar-hunger');
    const barValHunger = document.getElementById('bar-val-hunger');
    const barEnergy = document.getElementById('bar-energy');
    const barValEnergy = document.getElementById('bar-val-energy');
    const barHappiness = document.getElementById('bar-happiness');
    const barValHappiness = document.getElementById('bar-val-happiness');
    const barLove = document.getElementById('bar-love');
    const barValLove = document.getElementById('bar-val-love');
    const tamagotchiStatusBadge = document.getElementById('tamagotchi-status-badge');
    const actionButtons = document.querySelectorAll('.btn-action');

    // Manual Checkin Sliders
    const sliderHunger = document.getElementById('slider-hunger');
    const sliderEnergy = document.getElementById('slider-energy');
    const sliderHappiness = document.getElementById('slider-happiness');
    const sliderLove = document.getElementById('slider-love');

    const valHunger = document.getElementById('val-hunger');
    const valEnergy = document.getElementById('val-energy');
    const valHappiness = document.getElementById('val-happiness');
    const valLove = document.getElementById('val-love');

    const btnSaveCheckin = document.getElementById('btn-save-checkin');

    const speechBubble = document.getElementById('speech-bubble');
    const timeIntervalInput = document.getElementById('time-interval');
    const noteInput = document.getElementById('checkin-note');
    const btnSubmit = document.getElementById('btn-submit');
    const btnSos = document.getElementById('btn-sos');
    const chips = document.querySelectorAll('.tag-chip');
    const historyList = document.getElementById('history-list');

    // Reaction Modal / Toast elements
    const reactionModal = document.getElementById('reaction-modal');
    const reactionTitle = document.getElementById('reaction-title');
    const reactionBody = document.getElementById('reaction-body');
    const reactionClose = document.getElementById('reaction-close');

    const selectedTags = new Set(['Красивая сижу']);
    let isUserInteractingWithSliders = false;

    // -------------------------------------------------------------
    // 4. Default Time Interval Initialization (Current Hour)
    // -------------------------------------------------------------
    const updateDefaultTimeInterval = () => {
        const now = new Date();
        const startHour = String(now.getHours()).padStart(2, '0');
        const endHour = String((now.getHours() + 1) % 24).padStart(2, '0');
        if (timeIntervalInput) {
            timeIntervalInput.value = `${startHour}:00 - ${endHour}:00`;
        }
    };
    updateDefaultTimeInterval();

    // -------------------------------------------------------------
    // 5. Tamagotchi State & Realtime Care Actions
    // -------------------------------------------------------------
    const renderTamagotchiState = (data) => {
        if (!data) return;

        if (barHunger && barValHunger) {
            barHunger.style.width = `${data.hunger}%`;
            barValHunger.innerText = `${data.hunger}%`;
        }
        if (barEnergy && barValEnergy) {
            barEnergy.style.width = `${data.energy}%`;
            barValEnergy.innerText = `${data.energy}%`;
        }
        if (barHappiness && barValHappiness) {
            barHappiness.style.width = `${data.happiness}%`;
            barValHappiness.innerText = `${data.happiness}%`;
        }
        if (barLove && barValLove) {
            barLove.style.width = `${data.love}%`;
            barValLove.innerText = `${data.love}%`;
        }

        // Sync slider values when not actively dragging
        if (!isUserInteractingWithSliders) {
            if (sliderHunger) { sliderHunger.value = data.hunger; if (valHunger) valHunger.innerText = `${data.hunger}%`; }
            if (sliderEnergy) { sliderEnergy.value = data.energy; if (valEnergy) valEnergy.innerText = `${data.energy}%`; }
            if (sliderHappiness) { sliderHappiness.value = data.happiness; if (valHappiness) valHappiness.innerText = `${data.happiness}%`; }
            if (sliderLove) { sliderLove.value = data.love; if (valLove) valLove.innerText = `${data.love}%`; }
        }

        if (tamagotchiStatusBadge && data.status_text) {
            tamagotchiStatusBadge.innerText = data.status_text;
        }

        if (speechBubble && data.status_text) {
            speechBubble.innerText = data.status_text;
        }

        if (viewer) {
            if (data.mood) viewer.setMood(data.mood);
            viewer.updateLighting(data.happiness, data.energy);
        }
    };

    const fetchTamagotchiStatus = async () => {
        try {
            const resp = await fetch('/api/status');
            if (!resp.ok) return;
            const res = await resp.json();
            if (res.status === 'success' && res.data) {
                renderTamagotchiState(res.data);
            }
        } catch (e) {
            console.error('Error fetching tamagotchi status:', e);
        }
    };

    // Initial fetch and periodic poll every 12 seconds
    fetchTamagotchiStatus();
    setInterval(fetchTamagotchiStatus, 12000);

    // Handle Care Actions (feed, hug, sleep, miss)
    actionButtons.forEach(btn => {
        btn.addEventListener('click', async () => {
            const action = btn.getAttribute('data-action');
            if (!action) return;

            haptic('medium');

            // 3D Scene animation reaction immediately on click
            if (viewer) {
                if (action === 'hug' || action === 'miss') {
                    viewer.jumpAndSpin();
                } else if (action === 'feed') {
                    viewer.jumpAndSpin();
                } else if (action === 'sleep') {
                    viewer.setMood('tired');
                }
            }

            btn.disabled = true;
            btn.classList.add('opacity-70', 'scale-95');

            try {
                const resp = await fetch('/api/action', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action })
                });
                const res = await resp.json();

                if (res.status === 'success') {
                    haptic('success');
                    playCuteChime();
                    showNotificationToast(res.message, 'bg-rose-500 text-white');
                    renderTamagotchiState(res.data);
                } else if (res.status === 'cooldown') {
                    haptic('warning');
                    showNotificationToast(res.message, 'bg-amber-500 text-white');
                    if (res.data) renderTamagotchiState(res.data);
                } else {
                    showNotificationToast('Что-то пошло не так 😿', 'bg-rose-500 text-white');
                }
            } catch (err) {
                console.error('Action error:', err);
                haptic('error');
                showNotificationToast('Ошибка соединения с сервером', 'bg-rose-500 text-white');
            } finally {
                setTimeout(() => {
                    btn.disabled = false;
                    btn.classList.remove('opacity-70', 'scale-95');
                }, 300);
            }
        });
    });

    // -------------------------------------------------------------
    // 6. Dynamic Thoughts & Real-time Status Generator for Checkins
    // -------------------------------------------------------------
    const calculateStatusFromSliders = (hunger, energy, happiness, love) => {
        if (energy < 25) {
            return {
                text: "Хочет спать 😴💤",
                mood: "tired",
                bubble: "Батарейка на исходе... положите меня скорее в кроватку под одеялко 🪫😴"
            };
        } else if (hunger < 30) {
            return {
                text: "Срочно нужно покормить вкусняшкой! 🍰🥺",
                mood: "sad",
                bubble: "В животике играет грустный кит... Где же пицца или шоколад? 🍰🥺"
            };
        } else if (happiness < 35 || love < 35) {
            return {
                text: "Скучает по твоим объятиям 🥺💔",
                mood: "sad",
                bubble: "Срочно требуются твои объятия! Уровень милоты падает без тебя 🥺💕"
            };
        } else if (happiness >= 75 && hunger >= 70 && love >= 70) {
            return {
                text: "Сыта, счастлива и полна любви! ✨🥰",
                mood: "happy",
                bubble: "Мур! Я сыта, счастлива и полна любви к тебе! ✨🥰"
            };
        } else if (happiness >= 70) {
            return {
                text: "В прекрасном настроении ✨😊",
                mood: "happy",
                bubble: "Настроение чудесное, сижу красивая и вспоминаю тебя 🌸✨"
            };
        } else {
            return {
                text: "Всё хорошо, занимается делами 🌸",
                mood: "idle",
                bubble: "Всё отлично, сижу красивая и вспоминаю твою улыбку 🌸✨"
            };
        }
    };

    let checkinDebounceTimer = null;

    const onSliderChange = () => {
        if (!sliderHunger || !sliderEnergy || !sliderHappiness || !sliderLove) return;

        const hunger = parseInt(sliderHunger.value, 10);
        const energy = parseInt(sliderEnergy.value, 10);
        const happiness = parseInt(sliderHappiness.value, 10);
        const love = parseInt(sliderLove.value, 10);

        // Update slider value labels
        if (valHunger) valHunger.innerText = `${hunger}%`;
        if (valEnergy) valEnergy.innerText = `${energy}%`;
        if (valHappiness) valHappiness.innerText = `${happiness}%`;
        if (valLove) valLove.innerText = `${love}%`;

        // Synchronize top progress bars in real-time
        if (barHunger && barValHunger) {
            barHunger.style.width = `${hunger}%`;
            barValHunger.innerText = `${hunger}%`;
        }
        if (barEnergy && barValEnergy) {
            barEnergy.style.width = `${energy}%`;
            barValEnergy.innerText = `${energy}%`;
        }
        if (barHappiness && barValHappiness) {
            barHappiness.style.width = `${happiness}%`;
            barValHappiness.innerText = `${happiness}%`;
        }
        if (barLove && barValLove) {
            barLove.style.width = `${love}%`;
            barValLove.innerText = `${love}%`;
        }

        // Calculate dynamic status and update top badge + speech bubble
        const statusInfo = calculateStatusFromSliders(hunger, energy, happiness, love);
        if (tamagotchiStatusBadge) {
            tamagotchiStatusBadge.innerText = statusInfo.text;
        }

        let bubbleText = statusInfo.bubble;
        if (selectedTags.has('Хочу спать') && energy < 50) {
            bubbleText = "Зеваю уже десятый раз... снись мне сегодня, пожалуйста! 💤✨";
        } else if (selectedTags.has('Пью кофе')) {
            bubbleText = "Вкусный кофеек + мысли о тебе = идеальный час ☕💖";
        }

        if (speechBubble) {
            speechBubble.innerText = bubbleText;
        }

        if (viewer) {
            viewer.setMood(statusInfo.mood);
            viewer.updateLighting(happiness, energy);
        }

        haptic('light');

        // Debounce auto-save 1.5s after user stops dragging
        if (checkinDebounceTimer) clearTimeout(checkinDebounceTimer);
        checkinDebounceTimer = setTimeout(() => {
            sendCheckIn(true);
        }, 1500);
    };

    [sliderHunger, sliderEnergy, sliderHappiness, sliderLove].forEach(slider => {
        if (!slider) return;
        slider.addEventListener('input', onSliderChange);
        slider.addEventListener('mousedown', () => { isUserInteractingWithSliders = true; });
        slider.addEventListener('touchstart', () => { isUserInteractingWithSliders = true; }, { passive: true });
        slider.addEventListener('mouseup', () => { setTimeout(() => { isUserInteractingWithSliders = false; }, 2000); });
        slider.addEventListener('touchend', () => { setTimeout(() => { isUserInteractingWithSliders = false; }, 2000); });
    });

    // -------------------------------------------------------------
    // 7. Quick Tags (Chips) Interaction
    // -------------------------------------------------------------
    chips.forEach(chip => {
        const tagName = chip.getAttribute('data-tag');
        if (selectedTags.has(tagName)) {
            chip.classList.add('active-tag');
        }

        chip.addEventListener('click', () => {
            haptic('selection');
            if (selectedTags.has(tagName)) {
                selectedTags.delete(tagName);
                chip.classList.remove('active-tag');
            } else {
                selectedTags.add(tagName);
                chip.classList.add('active-tag');
            }
            onSliderChange();
        });
    });

    // -------------------------------------------------------------
    // 8. Submit Check-in Form & Save State
    // -------------------------------------------------------------
    const sendCheckIn = async (isDebounced = false) => {
        if (checkinDebounceTimer) {
            clearTimeout(checkinDebounceTimer);
            checkinDebounceTimer = null;
        }

        const hunger = parseInt(sliderHunger ? sliderHunger.value : 70, 10);
        const energy = parseInt(sliderEnergy ? sliderEnergy.value : 70, 10);
        const happiness = parseInt(sliderHappiness ? sliderHappiness.value : 85, 10);
        const love = parseInt(sliderLove ? sliderLove.value : 90, 10);

        const payload = {
            time_interval: (timeIntervalInput && timeIntervalInput.value.trim()) || "14:00 - 15:00",
            hunger: hunger,
            energy: energy,
            happiness: happiness,
            love: love,
            stress: Math.max(0, 100 - happiness),
            miss_you: love,
            tags: Array.from(selectedTags),
            note: (noteInput && noteInput.value.trim()) || '',
            is_sos: false
        };

        const submitText = btnSubmit ? btnSubmit.querySelector('.btn-text') : null;
        const submitSpinner = btnSubmit ? btnSubmit.querySelector('.btn-spinner') : null;

        if (!isDebounced) {
            if (submitText) submitText.classList.add('hidden');
            if (submitSpinner) submitSpinner.classList.remove('hidden');
            if (btnSubmit) btnSubmit.disabled = true;
            if (btnSaveCheckin) {
                btnSaveCheckin.disabled = true;
                btnSaveCheckin.classList.add('opacity-70', 'scale-95');
            }
            haptic('medium');
        }

        try {
            const resp = await fetch('/api/checkin', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await resp.json();

            if (resp.ok && data.status === 'success') {
                haptic('success');
                if (!isDebounced) {
                    playCuteChime();
                    showNotificationToast('✨ Чекин Лёли отправлен любимому в Telegram!', 'bg-emerald-500 text-white');
                    if (noteInput) noteInput.value = '';
                } else {
                    showNotificationToast('✨ Чекин Лёли сохранён и отправлен в Telegram!', 'bg-pink-500 text-white');
                }
                if (viewer) {
                    viewer.jumpAndSpin();
                }
                loadRecentHistory();
                fetchTamagotchiStatus();
            } else {
                throw new Error(data.message || 'Не удалось отправить');
            }
        } catch (err) {
            console.error('Checkin error:', err);
            if (!isDebounced) {
                haptic('error');
                showNotificationToast('Ошибка при отправке, попробуй снова 😿', 'bg-rose-500 text-white');
            }
        } finally {
            if (!isDebounced) {
                if (submitText) submitText.classList.remove('hidden');
                if (submitSpinner) submitSpinner.classList.add('hidden');
                if (btnSubmit) btnSubmit.disabled = false;
                if (btnSaveCheckin) {
                    btnSaveCheckin.disabled = false;
                    btnSaveCheckin.classList.remove('opacity-70', 'scale-95');
                }
            }
        }
    };

    if (btnSaveCheckin) {
        btnSaveCheckin.addEventListener('click', () => sendCheckIn(false));
    }
    if (btnSubmit) {
        btnSubmit.addEventListener('click', () => sendCheckIn(false));
    }

    // -------------------------------------------------------------
    // 9. Emergency SOS Ping Button
    // -------------------------------------------------------------
    if (btnSos) {
        btnSos.addEventListener('click', async () => {
            haptic('heavy');
            if (!confirm('Отправить экстренный SOS-пинг любимому? 🚨❤️')) return;

            btnSos.disabled = true;
            btnSos.classList.add('animate-pulse');

            const payload = {
                hunger: parseInt(sliderHunger ? sliderHunger.value : 50, 10),
                energy: parseInt(sliderEnergy ? sliderEnergy.value : 50, 10),
                happiness: parseInt(sliderHappiness ? sliderHappiness.value : 50, 10),
                love: parseInt(sliderLove ? sliderLove.value : 90, 10),
                stress: 80,
                miss_you: 100,
                note: (noteInput && noteInput.value.trim()) || 'Срочно похвали / скажи, что любишь! 🥺💖'
            };

            try {
                const resp = await fetch('/api/sos', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await resp.json();

                if (resp.ok) {
                    haptic('success');
                    showNotificationToast('🚨 SOS-алерт Лёли улетел парню с максимальным приоритетом!', 'bg-rose-600 text-white');
                    if (viewer) {
                        viewer.jumpAndSpin();
                    }
                    loadRecentHistory();
                } else {
                    throw new Error('SOS send failed');
                }
            } catch (err) {
                console.error('SOS error:', err);
                haptic('error');
                showNotificationToast('Не удалось отправить SOS 😿', 'bg-rose-500 text-white');
            } finally {
                btnSos.disabled = false;
                btnSos.classList.remove('animate-pulse');
            }
        });
    }

    // -------------------------------------------------------------
    // 10. Realtime Partner Reaction Polling
    // -------------------------------------------------------------
    const pollForReactions = async () => {
        try {
            const resp = await fetch('/api/reactions/latest');
            if (!resp.ok) return;
            const data = await resp.json();

            if (data.new_reactions && data.new_reactions.length > 0) {
                data.new_reactions.forEach(reaction => {
                    displayPartnerReaction(reaction);
                });
                loadRecentHistory();
                fetchTamagotchiStatus();
            }
        } catch (err) {
            // Silently retry on next poll
        }
    };

    // Poll every 4 seconds
    setInterval(pollForReactions, 4000);

    const displayPartnerReaction = (reaction) => {
        haptic('success');
        playCuteChime();

        // 3D Avatar effect
        if (viewer) {
            viewer.setMood('happy');
            viewer.jumpAndSpin();
        }

        // Show Reaction Modal
        if (reactionTitle) reactionTitle.innerText = reaction.label;
        if (reactionBody) reactionBody.innerText = reaction.message;
        if (reactionModal) {
            reactionModal.classList.remove('hidden');
            reactionModal.classList.add('flex');
        }

        // Dynamic thought update
        if (speechBubble) {
            speechBubble.innerText = `Ура! Любимый прислал реакцию: ${reaction.label} 🥰💖`;
        }
    };

    if (reactionClose && reactionModal) {
        reactionClose.addEventListener('click', () => {
            haptic('light');
            reactionModal.classList.add('hidden');
            reactionModal.classList.remove('flex');
        });
    }

    // -------------------------------------------------------------
    // 11. Toast Notifications Helper
    // -------------------------------------------------------------
    const showNotificationToast = (text, colorClass) => {
        const toast = document.createElement('div');
        toast.className = `fixed top-5 left-1/2 -translate-x-1/2 z-50 px-5 py-3 rounded-2xl shadow-xl font-medium text-sm flex items-center gap-2 transition-all transform duration-300 opacity-0 -translate-y-4 ${colorClass}`;
        toast.innerText = text;
        document.body.appendChild(toast);

        requestAnimationFrame(() => {
            toast.classList.remove('opacity-0', '-translate-y-4');
            toast.classList.add('opacity-100', 'translate-y-0');
        });

        setTimeout(() => {
            toast.classList.remove('opacity-100', 'translate-y-0');
            toast.classList.add('opacity-0', '-translate-y-4');
            setTimeout(() => toast.remove(), 350);
        }, 3200);
    };

    // -------------------------------------------------------------
    // 12. History Feed Loader
    // -------------------------------------------------------------
    const loadRecentHistory = async () => {
        try {
            const resp = await fetch('/api/checkins/recent');
            if (!resp.ok) return;
            const data = await resp.json();

            if (!historyList) return;
            historyList.innerHTML = '';

            if (!data.checkins || data.checkins.length === 0) {
                historyList.innerHTML = `<div class="text-center py-6 text-pink-300 text-xs font-light">Пока нет записей. Отправь первый отчёт! ✨</div>`;
                return;
            }

            data.checkins.forEach(c => {
                const item = document.createElement('div');
                item.className = 'bg-white/80 border border-pink-100/80 rounded-2xl p-3.5 shadow-sm space-y-2';

                const time = c.created_at ? c.created_at.split(' ')[1].slice(0, 5) : '';
                const tagsBadges = (c.tags || []).map(t => `<span class="bg-pink-50 text-pink-600 px-2 py-0.5 rounded-full text-[10px] font-semibold">#${t}</span>`).join(' ');

                const reactionsBadges = (c.reactions || []).map(r => `
                    <div class="mt-1.5 flex items-center gap-1.5 bg-rose-50 border border-rose-100 text-rose-700 px-2.5 py-1 rounded-xl text-xs font-medium">
                        <span>${r.label}</span>
                        <span class="text-[10px] text-rose-400">«${r.message}»</span>
                    </div>
                `).join('');

                item.innerHTML = `
                    <div class="flex items-center justify-between">
                        <span class="text-xs font-bold text-gray-800 flex items-center gap-1.5">
                            <span class="w-2 h-2 rounded-full ${c.is_sos ? 'bg-red-500 animate-ping' : 'bg-pink-400'}"></span>
                            ${c.time_interval}
                        </span>
                        <span class="text-[11px] text-gray-400">${time}</span>
                    </div>
                    <div class="grid grid-cols-4 gap-1 text-[11px] font-medium text-gray-600 bg-pink-50/50 p-2 rounded-xl">
                        <div>🍰 ${c.hunger}%</div>
                        <div>⚡ ${c.energy}%</div>
                        <div>✨ ${c.happiness !== undefined ? c.happiness : 85}%</div>
                        <div>❤️ ${c.love !== undefined ? c.love : 90}%</div>
                    </div>
                    ${c.note ? `<p class="text-xs text-gray-700 italic">«${c.note}»</p>` : ''}
                    ${tagsBadges ? `<div class="flex flex-wrap gap-1">${tagsBadges}</div>` : ''}
                    ${reactionsBadges}
                `;
                historyList.appendChild(item);
            });
        } catch (e) {
            console.error('History load error:', e);
        }
    };

    // Load history on start
    loadRecentHistory();
});
