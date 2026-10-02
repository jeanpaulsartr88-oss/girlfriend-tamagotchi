/**
 * 3D Avatar Viewer for Tamagotchi Girlfriend Live Monitoring TWA
 * Powered by Three.js & GLTFLoader with AnimationMixer & Procedural Fallbacks
 */

class GirlAvatarViewer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.clock = new THREE.Clock();
        this.mixer = null;
        this.actions = {};
        this.activeAction = null;
        this.model = null;
        this.proceduralCharacter = null;
        this.currentMood = 'idle';
        this.particles = [];
        this.heartBurstParticles = [];
        this.isStaticOrFallback = true;
        this.blinkingTimer = 0;
        this.isBlinking = false;

        this.init();
    }

    init() {
        if (!this.container) {
            console.error('Container element not found');
            return;
        }

        const width = this.container.clientWidth || window.innerWidth;
        const height = this.container.clientHeight || (window.innerHeight * 0.38);

        // 1. Scene
        this.scene = new THREE.Scene();

        // 2. Camera
        this.camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 100);
        this.camera.position.set(0, 1.15, 3.2);

        // 3. Renderer
        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
        this.renderer.setSize(width, height);
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        this.renderer.outputEncoding = THREE.sRGBEncoding;
        this.container.appendChild(this.renderer.domElement);

        // 4. Lighting
        this.setupLighting();

        // 5. Floor Shadow
        this.setupFloorShadow();

        // 6. Floating Ambient Particles (Hearts & Sparkles)
        this.setupAmbientParticles();

        // 7. Load GLB Model
        this.loadModel('/static/models/girl.glb');

        // 8. Event Listeners
        window.addEventListener('resize', () => this.onWindowResize());

        // 9. Interactive Touch/Mouse drag rotation
        this.setupInteractivity();

        // 10. Start Animation Loop
        this.animate = this.animate.bind(this);
        requestAnimationFrame(this.animate);
    }

    setupLighting() {
        // Soft ambient warm light
        const ambientLight = new THREE.AmbientLight(0xfff5f8, 0.9);
        this.scene.add(ambientLight);

        // Main key directional light with shadows
        const dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
        dirLight.position.set(2, 4, 3);
        dirLight.castShadow = true;
        dirLight.shadow.mapSize.width = 1024;
        dirLight.shadow.mapSize.height = 1024;
        dirLight.shadow.bias = -0.001;
        this.scene.add(dirLight);

        // Rim/Fill soft pink light
        const rimLight = new THREE.DirectionalLight(0xffb6c1, 0.8);
        rimLight.position.set(-2, 2, -2);
        this.scene.add(rimLight);

        // Subtle bottom bounce light
        const bounceLight = new THREE.PointLight(0xffd1dc, 0.5, 5);
        bounceLight.position.set(0, -0.5, 1.5);
        this.scene.add(bounceLight);
    }

    setupFloorShadow() {
        // Soft ground contact shadow circle
        const canvas = document.createElement('canvas');
        canvas.width = 128;
        canvas.height = 128;
        const ctx = canvas.getContext('2d');
        const grad = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
        grad.addColorStop(0, 'rgba(255, 182, 193, 0.45)');
        grad.addColorStop(0.5, 'rgba(230, 160, 180, 0.15)');
        grad.addColorStop(1, 'rgba(255, 255, 255, 0)');
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, 128, 128);

        const shadowGeo = new THREE.PlaneGeometry(1.8, 1.8);
        const shadowMat = new THREE.MeshBasicMaterial({
            map: new THREE.CanvasTexture(canvas),
            transparent: true,
            depthWrite: false
        });
        const shadowPlane = new THREE.Mesh(shadowGeo, shadowMat);
        shadowPlane.rotation.x = -Math.PI / 2;
        shadowPlane.position.y = -0.65;
        this.scene.add(shadowPlane);
    }

    setupAmbientParticles() {
        this.particlesGroup = new THREE.Group();
        this.scene.add(this.particlesGroup);

        const particleCount = 18;
        const heartShape = new THREE.Shape();
        heartShape.moveTo(0, 0);
        heartShape.bezierCurveTo(0, -0.05, -0.1, -0.05, -0.1, 0.05);
        heartShape.bezierCurveTo(-0.1, 0.12, 0, 0.15, 0, 0.22);
        heartShape.bezierCurveTo(0, 0.15, 0.1, 0.12, 0.1, 0.05);
        heartShape.bezierCurveTo(0.1, -0.05, 0, -0.05, 0, 0);

        const geom = new THREE.ShapeGeometry(heartShape);
        const mat = new THREE.MeshBasicMaterial({
            color: 0xff6b8b,
            side: THREE.DoubleSide,
            transparent: true,
            opacity: 0.65
        });

        for (let i = 0; i < particleCount; i++) {
            const mesh = new THREE.Mesh(geom, mat.clone());
            const scale = 0.08 + Math.random() * 0.12;
            mesh.scale.set(scale, scale, scale);
            mesh.rotation.z = Math.PI; // orient heart correctly
            mesh.position.set(
                (Math.random() - 0.5) * 2.2,
                -0.5 + Math.random() * 2.0,
                (Math.random() - 0.5) * 1.5
            );
            mesh.userData = {
                speedY: 0.003 + Math.random() * 0.005,
                swaySpeed: 1 + Math.random() * 2,
                swayDist: 0.003 + Math.random() * 0.004,
                rotSpeed: (Math.random() - 0.5) * 0.02,
                initialX: mesh.position.x
            };
            this.particles.push(mesh);
            this.particlesGroup.add(mesh);
        }
    }

    loadModel(url) {
        if (!THREE.GLTFLoader) {
            console.warn('GLTFLoader not found, building procedural character');
            this.buildProceduralChibiAvatar();
            return;
        }

        const loader = new THREE.GLTFLoader();
        loader.load(
            url,
            (gltf) => {
                const model = gltf.scene;
                this.model = model;

                // Center & scale model nicely
                const box = new THREE.Box3().setFromObject(model);
                const size = box.getSize(new THREE.Vector3());
                const center = box.getCenter(new THREE.Vector3());

                const maxDim = Math.max(size.x, size.y, size.z);
                const targetScale = maxDim > 0 ? (1.5 / maxDim) : 1;
                model.scale.set(targetScale, targetScale, targetScale);

                model.position.x = -center.x * targetScale;
                model.position.y = -center.y * targetScale + 0.15;
                model.position.z = -center.z * targetScale;

                // Enable shadows
                model.traverse((child) => {
                    if (child.isMesh) {
                        child.castShadow = true;
                        child.receiveShadow = true;
                        if (child.material) {
                            child.material.roughness = Math.min(child.material.roughness || 0.5, 0.7);
                        }
                    }
                });

                this.scene.add(model);

                // Handle Animations
                if (gltf.animations && gltf.animations.length > 0) {
                    console.log('[3D Viewer] Loaded animations:', gltf.animations.map(a => a.name));
                    this.mixer = new THREE.AnimationMixer(model);
                    this.isStaticOrFallback = false;

                    gltf.animations.forEach((clip) => {
                        const name = clip.name.toLowerCase();
                        const action = this.mixer.clipAction(clip);
                        this.actions[name] = action;

                        // Semantic aliases
                        if (name.includes('idle') || name.includes('breath') || name.includes('stand')) {
                            this.actions['idle'] = action;
                        } else if (name.includes('happy') || name.includes('dance') || name.includes('jump') || name.includes('cheer')) {
                            this.actions['happy'] = action;
                            this.actions['dance'] = action;
                        } else if (name.includes('tired') || name.includes('sleep') || name.includes('sit') || name.includes('low')) {
                            this.actions['tired'] = action;
                        } else if (name.includes('sad') || name.includes('angry') || name.includes('cry')) {
                            this.actions['sad'] = action;
                            this.actions['angry'] = action;
                        }
                    });

                    // Set default action
                    const defaultAction = this.actions['idle'] || this.actions[Object.keys(this.actions)[0]];
                    if (defaultAction) {
                        this.activeAction = defaultAction;
                        this.activeAction.play();
                    }
                } else {
                    console.log('[3D Viewer] GLB is static or placeholder; applying cute procedural stylization');
                    this.isStaticOrFallback = true;
                    // If model has only a basic mesh, supplement with cute chibi character
                    if (model.children.length <= 1) {
                        model.visible = false;
                        this.buildProceduralChibiAvatar();
                    }
                }
            },
            (xhr) => {
                // Progress
            },
            (error) => {
                console.warn('[3D Viewer] Error loading girl.glb, using procedural chibi character:', error);
                this.buildProceduralChibiAvatar();
            }
        );
    }

    /**
     * Builds a high quality, adorable 3D anime chibi girl character
     * Works instantly with zero external file dependencies!
     */
    buildProceduralChibiAvatar() {
        if (this.proceduralCharacter) return;

        const group = new THREE.Group();
        this.proceduralCharacter = group;

        // Materials
        const skinMat = new THREE.MeshToonMaterial({ color: 0xffdfd3 });
        const hairMat = new THREE.MeshToonMaterial({ color: 0x4a2e2b }); // Rich brunette / chocolate
        const blushMat = new THREE.MeshBasicMaterial({ color: 0xff6b8b, transparent: true, opacity: 0.55 });
        const eyeWhiteMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
        const pupilMat = new THREE.MeshBasicMaterial({ color: 0x3d2047 }); // Violet-brown anime eye
        const highlightMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
        const clothMat = new THREE.MeshToonMaterial({ color: 0xff69b4 }); // Cute bubblegum pink hoodie
        const collarMat = new THREE.MeshToonMaterial({ color: 0xffffff });
        const skirtMat = new THREE.MeshToonMaterial({ color: 0x7c3aed }); // Pastel purple skirt
        const bowMat = new THREE.MeshToonMaterial({ color: 0xff1493 });

        // 1. Head
        const headGeo = new THREE.SphereGeometry(0.38, 32, 32);
        headGeo.scale(1, 0.95, 1);
        const head = new THREE.Mesh(headGeo, skinMat);
        head.position.y = 0.52;
        head.castShadow = true;
        group.add(head);
        this.avatarHead = head;

        // 2. Hair: Bangs and Back
        const hairBackGeo = new THREE.SphereGeometry(0.42, 28, 28);
        const hairBack = new THREE.Mesh(hairBackGeo, hairMat);
        hairBack.position.set(0, 0.05, -0.05);
        head.add(hairBack);

        // Hair buns (twin cute buns)
        const bunGeo = new THREE.SphereGeometry(0.18, 20, 20);
        const leftBun = new THREE.Mesh(bunGeo, hairMat);
        leftBun.position.set(-0.35, 0.36, -0.05);
        head.add(leftBun);

        const rightBun = new THREE.Mesh(bunGeo, hairMat);
        rightBun.position.set(0.35, 0.36, -0.05);
        head.add(rightBun);

        // Ribbon bows on buns
        const bowGeo = new THREE.BoxGeometry(0.08, 0.08, 0.08);
        const leftBow = new THREE.Mesh(bowGeo, bowMat);
        leftBow.position.set(-0.28, 0.26, 0.1);
        head.add(leftBow);

        const rightBow = new THREE.Mesh(bowGeo, bowMat);
        rightBow.position.set(0.28, 0.26, 0.1);
        head.add(rightBow);

        // 3. Cute Anime Eyes
        this.leftEyeGroup = new THREE.Group();
        this.rightEyeGroup = new THREE.Group();

        // Eye shape
        const eyeGeo = new THREE.SphereGeometry(0.09, 16, 16);
        eyeGeo.scale(1, 1.25, 0.3);

        const leftEyeWhite = new THREE.Mesh(eyeGeo, eyeWhiteMat);
        const rightEyeWhite = new THREE.Mesh(eyeGeo, eyeWhiteMat);

        const pupilGeo = new THREE.SphereGeometry(0.065, 16, 16);
        pupilGeo.scale(1, 1.2, 0.35);
        const leftPupil = new THREE.Mesh(pupilGeo, pupilMat);
        leftPupil.position.set(0, -0.01, 0.02);
        leftEyeWhite.add(leftPupil);

        const rightPupil = new THREE.Mesh(pupilGeo, pupilMat);
        rightPupil.position.set(0, -0.01, 0.02);
        rightEyeWhite.add(rightPupil);

        // Eye highlights (sparkle in eyes)
        const highlightGeo = new THREE.SphereGeometry(0.025, 10, 10);
        const leftHighlight = new THREE.Mesh(highlightGeo, highlightMat);
        leftHighlight.position.set(-0.02, 0.035, 0.035);
        leftPupil.add(leftHighlight);

        const rightHighlight = new THREE.Mesh(highlightGeo, highlightMat);
        rightHighlight.position.set(-0.02, 0.035, 0.035);
        rightPupil.add(rightHighlight);

        this.leftEyeGroup.add(leftEyeWhite);
        this.leftEyeGroup.position.set(-0.13, 0.02, 0.33);

        this.rightEyeGroup.add(rightEyeWhite);
        this.rightEyeGroup.position.set(0.13, 0.02, 0.33);

        head.add(this.leftEyeGroup);
        head.add(this.rightEyeGroup);

        // 4. Blushing Cheeks
        const blushGeo = new THREE.SphereGeometry(0.06, 16, 16);
        blushGeo.scale(1.2, 0.6, 0.2);

        const leftBlush = new THREE.Mesh(blushGeo, blushMat);
        leftBlush.position.set(-0.21, -0.1, 0.3);
        head.add(leftBlush);

        const rightBlush = new THREE.Mesh(blushGeo, blushMat);
        rightBlush.position.set(0.21, -0.1, 0.3);
        head.add(rightBlush);

        // Cute smiling mouth
        const mouthGeo = new THREE.TorusGeometry(0.04, 0.012, 8, 16, Math.PI);
        const mouthMat = new THREE.MeshBasicMaterial({ color: 0x992b45 });
        const mouth = new THREE.Mesh(mouthGeo, mouthMat);
        mouth.rotation.x = Math.PI;
        mouth.position.set(0, -0.15, 0.35);
        head.add(mouth);
        this.avatarMouth = mouth;

        // 5. Body / Torso
        const bodyGeo = new THREE.CylinderGeometry(0.18, 0.26, 0.45, 20);
        const body = new THREE.Mesh(bodyGeo, clothMat);
        body.position.y = 0.15;
        body.castShadow = true;
        group.add(body);
        this.avatarBody = body;

        // Collar
        const collarGeo = new THREE.TorusGeometry(0.16, 0.035, 12, 24);
        const collar = new THREE.Mesh(collarGeo, collarMat);
        collar.rotation.x = Math.PI / 2;
        collar.position.y = 0.22;
        body.add(collar);

        // Skirt
        const skirtGeo = new THREE.ConeGeometry(0.36, 0.25, 24, 1, true);
        const skirt = new THREE.Mesh(skirtGeo, skirtMat);
        skirt.position.y = -0.18;
        body.add(skirt);

        // 6. Arms
        const armGeo = new THREE.CylinderGeometry(0.05, 0.05, 0.3, 12);
        armGeo.translate(0, -0.15, 0);

        this.leftArm = new THREE.Mesh(armGeo, clothMat);
        this.leftArm.position.set(-0.26, 0.16, 0);
        this.leftArm.rotation.z = 0.25;
        group.add(this.leftArm);

        this.rightArm = new THREE.Mesh(armGeo, clothMat);
        this.rightArm.position.set(0.26, 0.16, 0);
        this.rightArm.rotation.z = -0.25;
        group.add(this.rightArm);

        // Cute floating heart companion beside head
        const haloHeartShape = new THREE.Shape();
        haloHeartShape.moveTo(0, 0);
        haloHeartShape.bezierCurveTo(0, -0.04, -0.08, -0.04, -0.08, 0.04);
        haloHeartShape.bezierCurveTo(-0.08, 0.09, 0, 0.12, 0, 0.18);
        haloHeartShape.bezierCurveTo(0, 0.12, 0.08, 0.09, 0.08, 0.04);
        haloHeartShape.bezierCurveTo(0.08, -0.04, 0, -0.04, 0, 0);

        const haloHeartGeo = new THREE.ShapeGeometry(haloHeartShape);
        const haloHeartMat = new THREE.MeshBasicMaterial({ color: 0xff1493, side: THREE.DoubleSide });
        this.haloHeart = new THREE.Mesh(haloHeartGeo, haloHeartMat);
        this.haloHeart.scale.set(0.6, 0.6, 0.6);
        this.haloHeart.rotation.z = Math.PI;
        this.haloHeart.position.set(0.42, 0.85, 0.1);
        group.add(this.haloHeart);

        group.position.y = -0.15;
        this.scene.add(group);
        this.model = group;
        this.isStaticOrFallback = true;
    }

    setupInteractivity() {
        let isDragging = false;
        let prevMouseX = 0;

        const onStart = (clientX) => {
            isDragging = true;
            prevMouseX = clientX;
        };

        const onMove = (clientX) => {
            if (!isDragging || !this.model) return;
            const deltaX = clientX - prevMouseX;
            this.model.rotation.y += deltaX * 0.012;
            prevMouseX = clientX;
        };

        const onEnd = () => {
            isDragging = false;
        };

        this.container.addEventListener('mousedown', (e) => onStart(e.clientX));
        window.addEventListener('mousemove', (e) => onMove(e.clientX));
        window.addEventListener('mouseup', onEnd);

        this.container.addEventListener('touchstart', (e) => {
            if (e.touches.length === 1) onStart(e.touches[0].clientX);
        }, { passive: true });

        window.addEventListener('touchmove', (e) => {
            if (e.touches.length === 1) onMove(e.touches[0].clientX);
        }, { passive: true });

        window.addEventListener('touchend', onEnd);
    }

    setMood(mood) {
        if (this.currentMood === mood) return;
        this.currentMood = mood;
        console.log(`[3D Avatar] Switching mood to: ${mood}`);

        // If skeletal animation is available
        if (this.mixer && this.actions[mood]) {
            const nextAction = this.actions[mood];
            if (this.activeAction !== nextAction) {
                if (this.activeAction) {
                    this.activeAction.fadeOut(0.4);
                }
                nextAction.reset().fadeIn(0.4).play();
                this.activeAction = nextAction;
            }
        }
    }

    triggerHeartBurst() {
        console.log('[3D Viewer] Spawning Heart Burst Reaction!');
        const burstCount = 25;
        const heartShape = new THREE.Shape();
        heartShape.moveTo(0, 0);
        heartShape.bezierCurveTo(0, -0.05, -0.1, -0.05, -0.1, 0.05);
        heartShape.bezierCurveTo(-0.1, 0.12, 0, 0.15, 0, 0.22);
        heartShape.bezierCurveTo(0, 0.15, 0.1, 0.12, 0.1, 0.05);
        heartShape.bezierCurveTo(0.1, -0.05, 0, -0.05, 0, 0);

        const geom = new THREE.ShapeGeometry(heartShape);
        const colors = [0xff1493, 0xff69b4, 0xffd700, 0xff6b8b, 0xa855f7];

        for (let i = 0; i < burstCount; i++) {
            const mat = new THREE.MeshBasicMaterial({
                color: colors[i % colors.length],
                side: THREE.DoubleSide,
                transparent: true,
                opacity: 0.95
            });
            const mesh = new THREE.Mesh(geom, mat);
            const scale = 0.12 + Math.random() * 0.14;
            mesh.scale.set(scale, scale, scale);
            mesh.rotation.z = Math.PI;

            mesh.position.set(
                (Math.random() - 0.5) * 0.4,
                0.2 + (Math.random() - 0.5) * 0.3,
                0.2 + (Math.random() - 0.5) * 0.2
            );

            mesh.userData = {
                vx: (Math.random() - 0.5) * 0.035,
                vy: 0.03 + Math.random() * 0.04,
                vz: (Math.random() - 0.5) * 0.025,
                life: 1.0,
                decay: 0.012 + Math.random() * 0.008
            };

            this.heartBurstParticles.push(mesh);
            this.scene.add(mesh);
        }

        // Jump animation on model
        if (this.model) {
            this.jumpTimer = 0.6;
        }
    }

    animate() {
        requestAnimationFrame(this.animate);
        const delta = this.clock.getDelta();
        const time = this.clock.getElapsedTime();

        // 1. Skeletal Animation Mixer
        if (this.mixer) {
            this.mixer.update(delta);
        }

        // 2. Procedural Idle Motion & Mood Adjustments
        if (this.model) {
            let swayFreq = 1.6;
            let swayAmp = 0.06;
            let breatheFreq = 2.4;
            let breatheAmp = 0.03;

            // Mood modulations
            if (this.currentMood === 'happy') {
                swayFreq = 3.2;
                swayAmp = 0.12;
                breatheFreq = 4.0;
                breatheAmp = 0.06;
            } else if (this.currentMood === 'tired') {
                swayFreq = 0.8;
                swayAmp = 0.03;
                breatheFreq = 1.2;
                breatheAmp = 0.02;
            } else if (this.currentMood === 'sad' || this.currentMood === 'angry') {
                swayFreq = 1.2;
                swayAmp = 0.05;
                breatheFreq = 1.8;
            }

            // Always smooth procedural sway fallback (even if static GLB)
            const idleSway = Math.sin(time * swayFreq) * swayAmp;
            const idleBreathe = Math.sin(time * breatheFreq) * breatheAmp;

            if (this.isStaticOrFallback) {
                this.model.rotation.y = idleSway;
                this.model.position.y = -0.15 + idleBreathe;

                // Jump effect if triggered by reaction
                if (this.jumpTimer && this.jumpTimer > 0) {
                    this.jumpTimer -= delta;
                    this.model.position.y += Math.sin(this.jumpTimer * Math.PI / 0.6) * 0.25;
                }

                // Procedural avatar limbs & blinking
                if (this.avatarHead) {
                    this.avatarHead.rotation.z = Math.sin(time * 1.5) * 0.05;
                    this.avatarHead.rotation.x = Math.sin(time * 2.0) * 0.03;

                    // Eye blink cycle
                    this.blinkingTimer += delta;
                    if (this.blinkingTimer > 3.5) {
                        this.isBlinking = true;
                        if (this.leftEyeGroup && this.rightEyeGroup) {
                            this.leftEyeGroup.scale.y = 0.1;
                            this.rightEyeGroup.scale.y = 0.1;
                        }
                        if (this.blinkingTimer > 3.65) {
                            this.isBlinking = false;
                            this.blinkingTimer = 0;
                            if (this.leftEyeGroup && this.rightEyeGroup) {
                                this.leftEyeGroup.scale.y = 1.0;
                                this.rightEyeGroup.scale.y = 1.0;
                            }
                        }
                    }

                    // Floating halo heart
                    if (this.haloHeart) {
                        this.haloHeart.position.y = 0.85 + Math.sin(time * 3) * 0.06;
                        this.haloHeart.rotation.y = time * 2;
                    }

                    // Mood-specific arm poses
                    if (this.leftArm && this.rightArm) {
                        if (this.currentMood === 'happy') {
                            this.leftArm.rotation.z = 1.8 + Math.sin(time * 5) * 0.25;
                            this.rightArm.rotation.z = -1.8 - Math.sin(time * 5) * 0.25;
                        } else if (this.currentMood === 'tired') {
                            this.leftArm.rotation.z = 0.1;
                            this.rightArm.rotation.z = -0.1;
                            this.avatarHead.rotation.x = 0.15; // droop head
                        } else {
                            this.leftArm.rotation.z = 0.25 + Math.sin(time * 2) * 0.06;
                            this.rightArm.rotation.z = -0.25 - Math.sin(time * 2) * 0.06;
                        }
                    }
                }
            }
        }

        // 3. Update Ambient Floating Particles
        for (let p of this.particles) {
            p.position.y += p.userData.speedY;
            p.position.x = p.userData.initialX + Math.sin(time * p.userData.swaySpeed) * p.userData.swayDist;
            p.rotation.y += p.userData.rotSpeed;

            if (p.position.y > 1.6) {
                p.position.y = -0.5;
                p.userData.initialX = (Math.random() - 0.5) * 2.2;
            }
        }

        // 4. Update Heart Burst Particles
        for (let i = this.heartBurstParticles.length - 1; i >= 0; i--) {
            const hp = this.heartBurstParticles[i];
            hp.position.x += hp.userData.vx;
            hp.position.y += hp.userData.vy;
            hp.position.z += hp.userData.vz;
            hp.userData.life -= hp.userData.decay;
            hp.material.opacity = Math.max(0, hp.userData.life);
            hp.scale.multiplyScalar(0.98);

            if (hp.userData.life <= 0) {
                this.scene.remove(hp);
                this.heartBurstParticles.splice(i, 1);
            }
        }

        this.renderer.render(this.scene, this.camera);
    }

    onWindowResize() {
        if (!this.container || !this.renderer || !this.camera) return;
        const width = this.container.clientWidth;
        const height = this.container.clientHeight || (window.innerHeight * 0.38);

        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    }
}

window.GirlAvatarViewer = GirlAvatarViewer;
