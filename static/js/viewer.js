/**
 * 3D Avatar Viewer for Tamagotchi Girlfriend Live Monitoring TWA
 * Powered by Three.js & GLTFLoader with OrbitControls & Auto-rotation
 */

class GirlAvatarViewer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;
        this.clock = new THREE.Clock();
        this.modelPivot = null;
        this.currentMood = 'idle';
        this.ambientParticles = [];
        this.heartBurstParticles = [];
        this.shadowPlane = null;
        this.isLoaded = false;

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

        // 2. Camera: adjusted fov and position for mobile portrait screens
        this.camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 100);
        this.camera.position.set(0, 0.05, 3.2);

        // 3. Renderer
        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
        this.renderer.setSize(width, height);
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        if (THREE.sRGBEncoding) {
            this.renderer.outputEncoding = THREE.sRGBEncoding;
        }
        this.container.appendChild(this.renderer.domElement);

        // 4. Lighting: Warm Ambient + Soft Directional from front-top + Rim light
        this.setupLighting();

        // 5. Soft Contact Floor Shadow
        this.setupFloorShadow();

        // 6. OrbitControls: Horizontal-only drag rotation, zoom & pitch locked
        this.setupControls();

        // 7. Ambient Floating Hearts/Sparkles
        this.setupAmbientParticles();

        // 8. Load GLB Model
        this.loadModel('/static/models/girl.glb');

        // 9. Resize listener
        window.addEventListener('resize', () => this.onWindowResize());

        // 10. Start Animation Loop
        this.animate = this.animate.bind(this);
        requestAnimationFrame(this.animate);
    }

    setupLighting() {
        // Warm AmbientLight for soft pastel mood
        const ambientLight = new THREE.AmbientLight(0xfff4e8, 1.1);
        this.scene.add(ambientLight);

        // Soft DirectionalLight from front and top
        const dirLight = new THREE.DirectionalLight(0xffffff, 1.25);
        dirLight.position.set(1.5, 3.5, 2.5);
        dirLight.castShadow = true;
        dirLight.shadow.mapSize.width = 1024;
        dirLight.shadow.mapSize.height = 1024;
        dirLight.shadow.bias = -0.001;
        this.scene.add(dirLight);

        // Soft pinkish rim light from behind for silhouette highlight
        const rimLight = new THREE.DirectionalLight(0xffd1dc, 0.75);
        rimLight.position.set(-2, 2.5, -2);
        this.scene.add(rimLight);

        // Gentle front fill light
        const frontFill = new THREE.PointLight(0xffe4e6, 0.45, 6);
        frontFill.position.set(0, 0.2, 2.0);
        this.scene.add(frontFill);
    }

    setupFloorShadow() {
        // Procedural radial gradient for soft ground contact shadow
        const canvas = document.createElement('canvas');
        canvas.width = 256;
        canvas.height = 256;
        const ctx = canvas.getContext('2d');
        const grad = ctx.createRadialGradient(128, 128, 0, 128, 128, 128);
        grad.addColorStop(0, 'rgba(255, 140, 170, 0.42)');
        grad.addColorStop(0.45, 'rgba(240, 160, 185, 0.16)');
        grad.addColorStop(1, 'rgba(255, 255, 255, 0)');
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, 256, 256);

        const shadowGeo = new THREE.PlaneGeometry(1.6, 1.6);
        const shadowMat = new THREE.MeshBasicMaterial({
            map: new THREE.CanvasTexture(canvas),
            transparent: true,
            depthWrite: false
        });
        this.shadowPlane = new THREE.Mesh(shadowGeo, shadowMat);
        this.shadowPlane.rotation.x = -Math.PI / 2;
        this.shadowPlane.position.y = -0.92;
        this.scene.add(this.shadowPlane);
    }

    setupControls() {
        if (!THREE.OrbitControls) {
            console.warn('THREE.OrbitControls is not loaded');
            return;
        }

        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        // Requirement: Horizontal-only drag rotation, zoom & pitch locked
        this.controls.enableZoom = false;
        this.controls.enablePan = false;
        this.controls.minPolarAngle = Math.PI / 2;
        this.controls.maxPolarAngle = Math.PI / 2;
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.06;
        this.controls.target.set(0, 0, 0);
        this.controls.update();
    }

    setupAmbientParticles() {
        this.particlesGroup = new THREE.Group();
        this.scene.add(this.particlesGroup);

        const particleCount = 14;
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
            opacity: 0.6
        });

        for (let i = 0; i < particleCount; i++) {
            const mesh = new THREE.Mesh(geom, mat.clone());
            const scale = 0.07 + Math.random() * 0.1;
            mesh.scale.set(scale, scale, scale);
            mesh.rotation.z = Math.PI;
            mesh.position.set(
                (Math.random() - 0.5) * 2.2,
                -0.8 + Math.random() * 1.8,
                (Math.random() - 0.5) * 1.2
            );
            mesh.userData = {
                speedY: 0.003 + Math.random() * 0.004,
                swaySpeed: 1.2 + Math.random() * 1.8,
                swayDist: 0.003 + Math.random() * 0.004,
                rotSpeed: (Math.random() - 0.5) * 0.015,
                initialX: mesh.position.x
            };
            this.ambientParticles.push(mesh);
            this.particlesGroup.add(mesh);
        }
    }

    loadModel(url) {
        if (!THREE.GLTFLoader) {
            console.warn('GLTFLoader not found, building procedural avatar');
            this.buildProceduralChibiAvatar();
            return;
        }

        const loader = new THREE.GLTFLoader();
        loader.load(
            url,
            (gltf) => {
                const model = gltf.scene;

                // 1. Calculate BoundingBox
                const box = new THREE.Box3().setFromObject(model);
                const size = box.getSize(new THREE.Vector3());
                const center = box.getCenter(new THREE.Vector3());

                console.log('[3D Viewer] Loaded girl.glb. Size:', size, 'Center:', center);

                // 2. Center geometry exactly on X, Y, Z
                model.position.x = -center.x;
                model.position.y = -center.y;
                model.position.z = -center.z;

                // 3. Put into Pivot Group for clean rotation & scaling
                const pivot = new THREE.Group();
                pivot.add(model);

                // 4. Scale model so it fits neatly into mobile smartphone screen
                const maxDim = Math.max(size.x, size.y, size.z);
                const targetHeight = 1.95; // Fills ~80% of portrait canvas viewport comfortably
                const scale = maxDim > 0 ? (targetHeight / maxDim) : 1;
                pivot.scale.set(scale, scale, scale);

                // Align shadow plane just beneath character's feet
                if (this.shadowPlane) {
                    const scaledHalfHeight = (size.y * scale) / 2;
                    this.shadowPlane.position.y = -scaledHalfHeight - 0.04;
                    this.shadowPlane.scale.set(size.x * scale * 1.2, size.z * scale * 1.2, 1);
                }

                // Enable shadow casting and double sided textures
                model.traverse((child) => {
                    if (child.isMesh) {
                        child.castShadow = true;
                        child.receiveShadow = true;
                        if (child.material) {
                            child.material.side = THREE.DoubleSide;
                            if (child.material.map) {
                                child.material.map.encoding = THREE.sRGBEncoding;
                            }
                        }
                    }
                });

                this.modelPivot = pivot;
                this.scene.add(pivot);
                this.isLoaded = true;
            },
            undefined,
            (error) => {
                console.warn('[3D Viewer] Error loading girl.glb, using procedural fallback:', error);
                this.buildProceduralChibiAvatar();
            }
        );
    }

    buildProceduralChibiAvatar() {
        if (this.modelPivot) return;
        const pivot = new THREE.Group();

        const skinMat = new THREE.MeshToonMaterial({ color: 0xffdfd3 });
        const hairMat = new THREE.MeshToonMaterial({ color: 0x4a2e2b });
        const dressMat = new THREE.MeshToonMaterial({ color: 0xff69b4 });

        // Head
        const headGeo = new THREE.SphereGeometry(0.38, 32, 32);
        const head = new THREE.Mesh(headGeo, skinMat);
        head.position.y = 0.52;
        pivot.add(head);

        // Hair
        const hairGeo = new THREE.SphereGeometry(0.42, 28, 28);
        const hair = new THREE.Mesh(hairGeo, hairMat);
        hair.position.set(0, 0.05, -0.05);
        head.add(hair);

        // Body
        const bodyGeo = new THREE.CylinderGeometry(0.18, 0.28, 0.6, 20);
        const body = new THREE.Mesh(bodyGeo, dressMat);
        body.position.y = 0.05;
        pivot.add(body);

        this.modelPivot = pivot;
        this.scene.add(pivot);
        this.isLoaded = true;
    }

    setMood(mood) {
        this.currentMood = mood;
        console.log(`[3D Avatar] Mood updated to: ${mood}`);
    }

    triggerHeartBurst() {
        const burstCount = 28;
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
            const scale = 0.1 + Math.random() * 0.14;
            mesh.scale.set(scale, scale, scale);
            mesh.rotation.z = Math.PI;

            mesh.position.set(
                (Math.random() - 0.5) * 0.4,
                0.1 + (Math.random() - 0.5) * 0.3,
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
    }

    animate() {
        requestAnimationFrame(this.animate);
        const time = this.clock.getElapsedTime();

        // 1. Requirement: Slow continuous auto-rotation around Y axis in requestAnimationFrame
        if (this.modelPivot) {
            let rotSpeed = 0.007;
            if (this.currentMood === 'happy') rotSpeed = 0.012;
            else if (this.currentMood === 'tired') rotSpeed = 0.004;

            this.modelPivot.rotation.y += rotSpeed;

            // Gentle subtle breathing float
            this.modelPivot.position.y = Math.sin(time * 2.2) * 0.025;
        }

        // 2. Update OrbitControls damping
        if (this.controls) {
            this.controls.update();
        }

        // 3. Update Ambient Floating Particles
        for (let p of this.ambientParticles) {
            p.position.y += p.userData.speedY;
            p.position.x = p.userData.initialX + Math.sin(time * p.userData.swaySpeed) * p.userData.swayDist;
            p.rotation.y += p.userData.rotSpeed;

            if (p.position.y > 1.5) {
                p.position.y = -0.8;
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
