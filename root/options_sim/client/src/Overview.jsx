import MyContext from "./context.jsx";
import { useState, useContext } from "react";
import GeneralInfo from "./GeneralInfo.jsx";


//openExpiries.includes(i)

function Overview() {
    const {streamedData} = useContext(MyContext);
    const [openExpiries, setOpenExpiries] = useState([]);

    console.log('test');

    function Table(matrix) {
        //console.log('matrix.m.data:', matrix.matrix.data);
    return (
        
        <table border="1">
        <thead>
            <tr>
                <th>best bid</th>
                <th>best ask</th>
                <th>spread</th>
                <th>volume</th>
                <th>ltp</th>
                <th>moneyness</th>
                <th>iv</th>
                <th>strike</th>
                <th>iv</th>
                <th>moneyness</th>
                <th>ltp</th>
                <th>volume</th>
                <th>spread</th>
                <th>best ask</th>
                <th>best bid</th>
            </tr>
        </thead>
        <tbody>
            {matrix.matrix.data.map((row, i) => (
            <tr key={i}>
                {row.map((cell, j) => (
                <td key={j}>{cell}</td>
                ))}
            </tr>
            ))}
        </tbody>
    </table>
    
    )
}

console.log('streameddata:', streamedData);

    return (
        <>
            <div style={{display: "flex", flexDirection: "column", alignItems: "center", gap: "10px"}}>
            <GeneralInfo/>
            </div>
        
            {streamedData ? (
                <div>
                    {streamedData.expiries.map((exp, i) => (
                        <>
                            <div>Expiry: {exp}</div>
                            <Table matrix={streamedData.overview[i]} />
                        </>
                    ))}
                </div>
            ) : (
            <div style={{display: "flex", flexDirection: "column", alignItems: "center"}}
            >No data here yet</div>
            )
            }
        </>
    );
}

export default Overview;