import { db } from "./firebase.js";

import {
collection,
getDocs,
query,
orderBy
}
from "https://www.gstatic.com/firebasejs/11.10.0/firebase-firestore.js";

const usersDiv = document.getElementById("users");

async function loadUsers(){

usersDiv.innerHTML="Загрузка...";

const q=query(
collection(db,"users"),
orderBy("lastVisit","desc")
);

const snapshot=await getDocs(q);

usersDiv.innerHTML="";

snapshot.forEach(doc=>{

const u=doc.data();

const card=document.createElement("div");

card.className="card";

card.innerHTML=`

<div class="username">

@${u.username || "без ника"}

</div>

<div class="info">

Имя: ${u.first_name || "-"}

</div>

<div class="info">

Посещений: ${u.visitsCount || 0}

</div>

<div class="info">

Последний вход:

${u.lastVisit || "-"}

</div>

<button>

История посещений

</button>

`;

card.querySelector("button").onclick=()=>{

showVisits(u);

};

usersDiv.appendChild(card);

});

}

function showVisits(user){

let text="";

if(user.visits){

user.visits.forEach(v=>{

text+=v+"\\n";

});

}else{

text="История отсутствует";

}

alert(text);

}

loadUsers();
