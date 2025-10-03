
import {Link} from "react-router-dom";

function NavBar() {
    return (
        <div style={{
            display: "flex",
            justifyContent: "center",
            gap: "20px",
            marginBottom: "20px"
        }}>
            <Link to="/">Settings & Control</Link>
            <Link to="/orderbooks">OrderBooks</Link>
            <Link to="/overview">Overview</Link>
        </div>
    )
}

export default NavBar;