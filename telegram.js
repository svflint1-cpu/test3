import { db } from "./firebase.js";

import {
doc,
getDoc,
setDoc,
updateDoc,
arrayUnion,
increment
} from "https://www.gstatic.com/firebasejs/11.10.0/firebase-firestore.js";

const tg = window.Telegram.WebApp;

tg.ready();

const user = tg.initDataUnsafe.user;

if(!user){

    console.log("Открыто не через Telegram");

}else{

    saveUser(user);

}

async function saveUser(user){

    const now = new Date();

    const date = now.toLocaleString("ru-RU");

    const ref = doc(db,"users",String(user.id));

    const snap = await getDoc(ref);

    if(!snap.exists()){

        await setDoc(ref,{

            telegramId:user.id,

            username:user.username || "",

            first_name:user.first_name || "",

            last_name:user.last_name || "",

            firstVisit:date,

            lastVisit:date,

            visitsCount:1,

            visits:[date]

        });

        return;

    }

    await updateDoc(ref,{

        lastVisit:date,

        visitsCount:increment(1),

        visits:arrayUnion(date)

    });

}
